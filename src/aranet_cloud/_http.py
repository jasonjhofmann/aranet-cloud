"""Low-level HTTP wrapper.

Handles aiohttp session lifecycle, ApiKey header injection, retry/backoff
for transient failures, polite-spacing, and error-response classification.

The high-level :class:`AranetCloudClient` uses this internally. End users
should not need to touch it directly.
"""

from __future__ import annotations

import asyncio
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

        text, status = await self._request_with_retry(url, params=clean_params, accept=accept)

        if status == 200:
            if not text or text == "{}":
                # Aranet returns 200 with empty/{} body for queries that match
                # no data. Treat as "empty dict" rather than a parse error.
                return {}
            try:
                import json
                return json.loads(text)  # type: ignore[no-any-return]
            except ValueError as err:
                raise AranetServerError(
                    f"Malformed JSON in 200 response: {err}", status=status
                ) from err

        self._raise_for_status(status, text)
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
        await self._respect_min_interval()
        headers = self._headers(accept="*/*")
        last_err: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                async with session.get(
                    url, params=clean_params, headers=headers, timeout=self._timeout
                ) as resp:
                    if resp.status == 200:
                        self._last_request_at = time.monotonic()
                        return await resp.read()
                    text = await resp.text()
                    if resp.status in (500, 502, 503, 504) and attempt < self._max_retries:
                        await self._sleep_backoff(attempt)
                        continue
                    self._raise_for_status(resp.status, text)
            except aiohttp.ClientError as err:
                last_err = err
                if attempt < self._max_retries:
                    await self._sleep_backoff(attempt)
                    continue
                raise AranetConnectionError(str(err)) from err
        # Defensive — shouldn't reach here.
        raise AranetConnectionError(str(last_err) if last_err else "exhausted retries")

    # -- internal -------------------------------------------------------

    async def _request_with_retry(
        self,
        url: str,
        *,
        params: Mapping[str, Any],
        accept: str,
    ) -> tuple[str, int]:
        session = await self._ensure_session()
        headers = self._headers(accept=accept)
        last_err: Exception | None = None
        for attempt in range(self._max_retries + 1):
            await self._respect_min_interval()
            try:
                async with session.get(
                    url, params=params, headers=headers, timeout=self._timeout
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
                    return text, resp.status
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
        """Exponential backoff with cap. Override accepts a server-supplied
        ``Retry-After`` value (seconds, as a string)."""
        if override:
            try:
                delay = float(override)
            except ValueError:
                delay = DEFAULT_BACKOFF_BASE
        else:
            delay = min(DEFAULT_BACKOFF_BASE * (2**attempt), DEFAULT_BACKOFF_CAP)
        _LOGGER.debug("backoff: sleeping %.2fs before retry", delay)
        await asyncio.sleep(delay)

    def _raise_for_status(self, status: int, body: str) -> None:
        """Translate a non-200 status into the appropriate exception type."""
        if status == 401:
            # Aranet returns plain text here: "Invalid ApiKey" / "Not Authorized"
            raise AranetAuthError(body.strip() or "Unauthorized")
        if status == 404:
            raise AranetNotFoundError(body.strip() or "Not found")
        if status == 429:
            retry_after: float | None = None
            try:
                retry_after = float(body) if body.strip() else None
            except ValueError:
                retry_after = None
            raise AranetRateLimitError(body.strip() or "Rate limited", retry_after=retry_after)
        if status == 400:
            # Aranet returns JSON: {"error": [{"message": "...", "id": "..."}]}
            correlation: str | None = None
            message = body
            try:
                import json
                parsed = json.loads(body) if body else {}
                errs = parsed.get("error") if isinstance(parsed, Mapping) else None
                if isinstance(errs, list) and errs:
                    detail = ErrorDetail.from_dict(errs[0])
                    message = detail.message or body
                    correlation = detail.id or None
            except ValueError:
                pass
            raise AranetValidationError(message, correlation_id=correlation)
        if 500 <= status < 600:
            raise AranetServerError(body.strip() or f"Server error {status}", status=status)
        # Any other unexpected status — surface it.
        raise AranetServerError(f"Unexpected status {status}: {body[:200]}", status=status)
