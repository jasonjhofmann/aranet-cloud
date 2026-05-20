"""Exception hierarchy.

All exceptions derive from :class:`AranetError`. Callers can catch the base
class to handle any library-raised error, or catch specific subclasses to
react differentially (401 vs 400 vs network).

Auth errors (401) deserve special handling — the Aranet API returns these
as **plain text** bodies (``Invalid ApiKey`` / ``Not Authorized``), not JSON,
so :class:`AranetAuthError` does NOT carry a ``correlation_id``. Validation
errors (400) DO carry one in ``error[].id``.
"""

from __future__ import annotations


class AranetError(Exception):
    """Base class for all aranet-cloud errors. Catch this for a blanket handler."""


class AranetConnectionError(AranetError):
    """Network-level failure: timeout, DNS, TLS, connection reset.

    Raised when the request never reached the API or no parseable response came
    back. Transient — the caller may retry. The library's own retry policy has
    already given up by the time this surfaces.
    """


class AranetServerError(AranetError):
    """5xx response from the API after exhausted retries.

    Transient on Aranet's side; safe to retry later. ``status`` carries the
    actual code.
    """

    def __init__(self, message: str, *, status: int) -> None:
        super().__init__(message)
        self.status = status


class AranetAuthError(AranetError):
    """401 Unauthorized — API key is wrong, missing, or revoked.

    Not transient. The user must rotate or re-enter their key. HA integrations
    should surface this via the Repairs flow.
    """

    def __init__(self, message: str = "Invalid or missing API key") -> None:
        super().__init__(message)


class AranetValidationError(AranetError):
    """400 Bad Request — the API rejected a parameter.

    Aranet returns a JSON body like::

        {"error": [{"message": "...", "id": "<correlation>"}]}

    The correlation token is preserved on ``correlation_id`` and should be
    logged so users can ask Aranet support to trace a request server-side.
    """

    def __init__(self, message: str, *, correlation_id: str | None = None) -> None:
        super().__init__(message)
        self.correlation_id = correlation_id


class AranetRateLimitError(AranetError):
    """429 Too Many Requests.

    Not observed in production at the consumer tier as of late-2026, but the
    library handles it defensively. ``retry_after`` carries the server's hint
    (seconds) if present.
    """

    def __init__(self, message: str = "Rate limited", *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class AranetNotFoundError(AranetError):
    """404 — endpoint or resource not found.

    Rarer than expected on this API; many "missing data" cases return ``200 {}``
    rather than 404. Still raised when the API explicitly returns 404.
    """
