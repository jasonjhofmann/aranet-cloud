"""Low-level HTTP wrapper.

Handles aiohttp session lifecycle, ApiKey header injection, retry/backoff
for transient failures, polite-spacing, and error-response classification.

The high-level :class:`AranetCloudClient` uses this internally. End users
should not need to touch it directly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from .const import (
    API_KEY_HEADER,
    DEFAULT_BACKOFF_BASE,
    DEFAULT_BACKOFF_CAP,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    MIN_REQUEST_INTERVAL,
    USER_AGENT,
)
from .exceptions import (
    AranetAuthError,
    AranetConnectionError,
    AranetError,
    AranetNotFoundError,
    AranetRateLimitError,
    AranetServerError,
    AranetValidationError,
)
from .models import ErrorDetail

_LOGGER = logging.getLogger("aranet_cloud")


class _Transport:
    """Internal HTTP transport. Not part of the public API.

    Lifecycle:

    * If created with ``session=None``, lazily allocates an ``aiohttp.ClientSession``
      on first request and closes it on :meth:`close`.
    * If a session is passed in, the transport never closes it — the caller
      retains ownership (this is the HA-friendly pattern; HA injects its
      ``aiohttp_client.async_get_clientsession(hass)``).

    The class is async-context-manager-compatible::

        async with _Transport(api_key="...") as t:
            data = await t.get_json("/api/v1/sensors")
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        session: aiohttp.ClientSession | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        user_agent: str = USER_AGENT,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must be non-empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._max_retries = max(0, max_retries)
        self._user_agent = user_agent
        self._session = session
        self._owns_session = session is None
        self._last_request_at = 0.0
        self._lock = asyncio.Lock()

    # -- session management ------------------------------------------------

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Close the underlying session if we created it."""
        if self._owns_session and self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def __aenter__(self) -> _Transport:
        await self._ensure_session()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # -- request --------------------------------------------------------

    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        accept: str = "application/json",
    ) -> dict[str, Any]:
        """GET *path* with retries; parse and return JSON body.

        ``path`` may be a relative path (joined to ``base_url``) or a full URL
        (e.g. a ``next`` link from a paginated response). ``params`` are
        appended as URL query string; ``None``-valued entries are dropped.
        """
        url = self._resolve_url(path)
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}

        text, status, retry_after = await self._request_with_retry(
            url, params=clean_params, accept=accept
        )

        if status == 200:
            if not text or text == "{}":
                # Aranet returns 200 with empty/{} body for queries that match
                # no data. Treat as "empty dict" rather than a parse error.
                return {}
            try:
                parsed = json.loads(text)
            except ValueError as err:
                raise AranetServerError(
                    f"Malformed JSON in 200 response: {err}", status=status
                ) from err
            if not isinstance(parsed, dict):
                # The API contract is a JSON object at the top level. A bare
                # array/string/number would crash callers (`.get(...)`) with
                # an AttributeError outside the AranetError hierarchy.
                raise AranetServerError(
                    f"Expected JSON object in 200 response, got {type(parsed).__name__}",
                    status=status,
                )
            return parsed

        self._raise_for_status(status, text, retry_after=retry_after)
        # _raise_for_status always raises on non-200; this line is unreachable
        # but keeps mypy happy on the return type.
        raise AssertionError("unreachable")

    async def get_bytes(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> bytes:
        """GET *path* and return the raw response body (for binary attachments)."""
        url = self._resolve_url(path)
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}

        session = await self._ensure_session()
        headers = self._headers(accept="*/*")
        last_err: Exception | None = None
        # Redirects are left enabled here (unlike the JSON path): a binary
        # attachment may legitimately 30x to a blob/CDN URL. The JSON API
        # endpoints never redirect, so that path refuses to (see
        # _request_with_retry) to avoid leaking the ApiKey cross-origin.
        for attempt in range(self._max_retries + 1):
            await self._respect_min_interval()
            try:
                async with session.get(
                    url, params=clean_params, headers=headers, timeout=self._timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        self._last_request_at = time.monotonic()
                        _LOGGER.debug(
                            "GET %s params=%s → 200 (%d bytes)",
                            url, dict(clean_params), len(data),
                        )
                        return data
                    text = await resp.text()
                    self._last_request_at = time.monotonic()
                    _LOGGER.debug(
                        "GET %s params=%s → %s (%d bytes)",
                        url, dict(clean_params), resp.status, len(text),
                    )
                    if resp.status in (500, 502, 503, 504) and attempt < self._max_retries:
                        await self._sleep_backoff(attempt)
                        continue
                    if resp.status == 429 and attempt < self._max_retries:
                        await self._sleep_backoff(
                            attempt, override=resp.headers.get("Retry-After")
                        )
                        continue
                    self._raise_for_status(
                        resp.status, text, retry_after=resp.headers.get("Retry-After")
                    )
            except aiohttp.ClientError as err:
                last_err = err
                _LOGGER.warning(
                    "network error on attempt %d/%d: %s",
                    attempt + 1, self._max_retries + 1, err,
                )
                if attempt < self._max_retries:
                    await self._sleep_backoff(attempt)
                    continue
                raise AranetConnectionError(str(err)) from err
            except TimeoutError as err:
                last_err = err
                _LOGGER.warning(
                    "timeout on attempt %d/%d", attempt + 1, self._max_retries + 1
                )
                if attempt < self._max_retries:
                    await self._sleep_backoff(attempt)
                    continue
                raise AranetConnectionError("request timed out") from err
        # Defensive — shouldn't reach here.
        raise AranetConnectionError(str(last_err) if last_err else "exhausted retries")

    # -- internal -------------------------------------------------------

    async def _request_with_retry(
        self,
        url: str,
        *,
        params: Mapping[str, Any],
        accept: str,
    ) -> tuple[str, int, str | None]:
        """GET with retries; return ``(body, status, retry_after_header)``.

        ``retry_after_header`` is the final response's ``Retry-After`` value
        (or ``None``), preserved so :meth:`_raise_for_status` can attach it to
        :class:`AranetRateLimitError` after retries are exhausted.
        """
        session = await self._ensure_session()
        headers = self._headers(accept=accept)
        last_err: Exception | None = None
        for attempt in range(self._max_retries + 1):
            await self._respect_min_interval()
            try:
                # allow_redirects=False: the JSON API endpoints are not
                # documented to redirect. Following a server-supplied 30x would
                # re-send the ApiKey header to the redirect target — possibly a
                # foreign origin — defeating the same-origin pin in _resolve_url.
                # A redirect here is anomalous, so surface it instead.
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self._timeout,
                    allow_redirects=False,
                ) as resp:
                    text = await resp.text()
                    self._last_request_at = time.monotonic()
                    _LOGGER.debug(
                        "GET %s params=%s → %s (%d bytes)",
                        url, dict(params), resp.status, len(text),
                    )
                    if resp.status in (500, 502, 503, 504) and attempt < self._max_retries:
                        await self._sleep_backoff(attempt)
                        continue
                    if resp.status == 429 and attempt < self._max_retries:
                        retry_after = resp.headers.get("Retry-After")
                        await self._sleep_backoff(attempt, override=retry_after)
                        continue
                    return text, resp.status, resp.headers.get("Retry-After")
            except aiohttp.ClientError as err:
                last_err = err
                _LOGGER.warning("network error on attempt %d/%d: %s", attempt + 1, self._max_retries + 1, err)
                if attempt < self._max_retries:
                    await self._sleep_backoff(attempt)
                    continue
                raise AranetConnectionError(str(err)) from err
            except TimeoutError as err:
                last_err = err
                _LOGGER.warning("timeout on attempt %d/%d", attempt + 1, self._max_retries + 1)
                if attempt < self._max_retries:
                    await self._sleep_backoff(attempt)
                    continue
                raise AranetConnectionError("request timed out") from err
        raise AranetConnectionError(str(last_err) if last_err else "exhausted retries")

    def _resolve_url(self, path: str) -> str:
        """Join *path* to ``base_url``, or validate an absolute URL.

        Absolute URLs (e.g. server-supplied ``next`` pagination links) are
        only followed when their origin (scheme + host + port) matches the
        configured ``base_url`` — every request carries the ``ApiKey``
        header, so following an arbitrary host (or an https→http downgrade)
        would leak credentials.
        """
        if not path.startswith(("http://", "https://")):
            return f"{self._base_url}{path}"
        base = urlsplit(self._base_url)
        target = urlsplit(path)
        if (target.scheme.lower(), target.netloc.lower()) != (
            base.scheme.lower(),
            base.netloc.lower(),
        ):
            raise AranetError(
                "Refusing to follow server-supplied URL with foreign origin "
                f"{target.scheme}://{target.netloc} (expected {base.scheme}://{base.netloc})"
            )
        return path

    def _headers(self, *, accept: str) -> dict[str, str]:
        return {
            API_KEY_HEADER: self._api_key,
            "Accept": accept,
            "User-Agent": self._user_agent,
        }

    async def _respect_min_interval(self) -> None:
        """Sleep if the previous request was very recent.

        Holds an asyncio lock so concurrent callers serialize. Cheap insurance
        against accidental hammering — Aranet hasn't documented a rate limit
        but we still don't want to be the integration that triggers one.
        """
        async with self._lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < MIN_REQUEST_INTERVAL:
                await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)

    async def _sleep_backoff(self, attempt: int, *, override: str | None = None) -> None:
        """Exponential backoff, clamped to :data:`DEFAULT_BACKOFF_CAP`.

        ``override`` accepts a server-supplied ``Retry-After`` value
        (delta-seconds, as a string). Both the exponential and the override
        paths are clamped to the cap so a hostile or misconfigured upstream
        cannot make the client sleep for an unbounded time inside an awaited
        request — that would silently wedge a polling caller (e.g. an HA
        ``DataUpdateCoordinator``). HTTP-date forms of ``Retry-After`` are not
        parsed and fall back to the base delay.
        """
        if override:
            try:
                delay = float(override)
            except ValueError:
                delay = DEFAULT_BACKOFF_BASE
        else:
            delay = DEFAULT_BACKOFF_BASE * (2**attempt)
        delay = min(delay, DEFAULT_BACKOFF_CAP)
        _LOGGER.debug("backoff: sleeping %.2fs before retry", delay)
        await asyncio.sleep(delay)

    def _raise_for_status(
        self, status: int, body: str, *, retry_after: str | None = None
    ) -> None:
        """Translate a non-200 status into the appropriate exception type.

        ``retry_after`` is the response's ``Retry-After`` header value, used
        to populate :class:`AranetRateLimitError.retry_after` on 429.
        """
        if status == 401:
            # Aranet returns plain text here: "Invalid ApiKey" / "Not Authorized"
            raise AranetAuthError(body.strip() or "Unauthorized")
        if status == 404:
            raise AranetNotFoundError(body.strip() or "Not found")
        if status == 429:
            retry_after_s: float | None = None
            if retry_after:
                try:
                    retry_after_s = float(retry_after)
                except ValueError:
                    retry_after_s = None
            raise AranetRateLimitError(
                body.strip() or "Rate limited", retry_after=retry_after_s
            )
        if status == 400:
            # Aranet returns JSON: {"error": [{"message": "...", "id": "..."}]}
            correlation: str | None = None
            message = body
            try:
                parsed: Any = json.loads(body) if body else {}
            except ValueError:
                parsed = {}
            errs = parsed.get("error") if isinstance(parsed, Mapping) else None
            # Guard every shape: errs may be absent, not a list, or contain a
            # non-Mapping first item (a bare string) — none of which may crash
            # the error path with an AttributeError outside AranetError.
            if isinstance(errs, list) and errs and isinstance(errs[0], Mapping):
                detail = ErrorDetail.from_dict(errs[0])
                message = detail.message or body
                correlation = detail.id or None
            raise AranetValidationError(message, correlation_id=correlation)
        if 500 <= status < 600:
            raise AranetServerError(body.strip() or f"Server error {status}", status=status)
        # Any other unexpected status — surface it.
        raise AranetServerError(f"Unexpected status {status}: {body[:200]}", status=status)
