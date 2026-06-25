"""Client-level tests via ``aioresponses``.

These mock the HTTP layer entirely — no live API calls. They verify:

* request paths + headers (esp. ``ApiKey`` header)
* response parsing
* pagination follows ``next`` correctly
* error responses raise the right exception subclass
* retry/backoff on 5xx and network errors
"""

from __future__ import annotations

import asyncio
import re

import pytest
from aioresponses import aioresponses

from aranet_cloud import (
    AranetAuthError,
    AranetCloudClient,
    AranetConnectionError,
    AranetError,
    AranetRateLimitError,
    AranetServerError,
    AranetValidationError,
)


@pytest.fixture
def api_key() -> str:
    return "test-api-key-DO-NOT-USE"


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


async def test_get_sensors_happy_path(api_key, sensors_payload):
    with aioresponses() as m:
        m.get("https://aranet.cloud/api/v1/sensors", payload=sensors_payload)
        async with AranetCloudClient(api_key=api_key) as client:
            sensors = await client.get_sensors()
        assert len(sensors) == 13
        assert any(s.name == "Bedroom" for s in sensors)


async def test_get_sensors_sends_apikey_header(api_key, sensors_payload):
    with aioresponses() as m:
        m.get("https://aranet.cloud/api/v1/sensors", payload=sensors_payload)
        async with AranetCloudClient(api_key=api_key) as client:
            await client.get_sensors()
        # aioresponses records each call with its kwargs incl. headers.
        call = next(iter(m.requests.values()))[0]
        assert call.kwargs["headers"]["ApiKey"] == api_key


async def test_get_sensors_with_base_filter_passes_param(api_key):
    with aioresponses() as m:
        m.get(
            "https://aranet.cloud/api/v1/sensors?base=358151000000001",
            payload={"sensors": []},
        )
        async with AranetCloudClient(api_key=api_key) as client:
            sensors = await client.get_sensors(base="358151000000001")
        assert sensors == []


async def test_get_measurements_last(api_key, measurements_last_payload):
    with aioresponses() as m:
        m.get(
            re.compile(r"https://aranet\.cloud/api/v1/measurements/last.*"),
            payload=measurements_last_payload,
        )
        async with AranetCloudClient(api_key=api_key) as client:
            readings, links = await client.get_measurements_last()
        assert len(readings) == 4
        assert links.name("metric", "3") == "CO₂"


# ---------------------------------------------------------------------------
# error responses
# ---------------------------------------------------------------------------


async def test_auth_error_raises_aranet_auth_error(api_key):
    with aioresponses() as m:
        m.get(
            "https://aranet.cloud/api/v1/sensors",
            status=401,
            body="Invalid ApiKey",
        )
        async with AranetCloudClient(api_key=api_key) as client:
            with pytest.raises(AranetAuthError, match="Invalid ApiKey"):
                await client.get_sensors()


async def test_validation_error_carries_correlation_id(api_key):
    with aioresponses() as m:
        m.get(
            re.compile(r"https://aranet\.cloud/api/v1/measurements/history.*"),
            status=400,
            payload={"error": [{"message": "Invalid time parameter not-a-date", "id": "d86fu2jf9lnc739nt3n0"}]},
        )
        async with AranetCloudClient(api_key=api_key) as client:
            with pytest.raises(AranetValidationError) as exc_info:
                async for _ in client.iter_measurements_history(from_="not-a-date"):
                    pass
        assert exc_info.value.correlation_id == "d86fu2jf9lnc739nt3n0"
        assert "Invalid time parameter" in str(exc_info.value)


async def test_empty_object_response_treated_as_no_data(api_key):
    """Aranet returns `200 {}` when a query matches no data — must not crash."""
    with aioresponses() as m:
        m.get(
            re.compile(r"https://aranet\.cloud/api/v1/measurements/last.*"),
            status=200,
            body="{}",
        )
        async with AranetCloudClient(api_key=api_key) as client:
            readings, links = await client.get_measurements_last(sensor="99999999")
        assert readings == []
        assert links.by_kind == {}


# ---------------------------------------------------------------------------
# retry / backoff
# ---------------------------------------------------------------------------


async def test_5xx_then_success_retries(api_key, sensors_payload, monkeypatch):
    """A transient 500 should be retried; second attempt succeeds."""
    # Patch sleep to zero so retries don't slow the test down.
    async def _noop_sleep(*_a, **_kw):
        return None
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    with aioresponses() as m:
        # aioresponses pops a registered response per matching call,
        # so chain a 503 then a 200.
        m.get("https://aranet.cloud/api/v1/sensors", status=503, body="busy")
        m.get("https://aranet.cloud/api/v1/sensors", payload=sensors_payload)

        async with AranetCloudClient(api_key=api_key, max_retries=2) as client:
            sensors = await client.get_sensors()
        assert len(sensors) == 13


async def test_5xx_exhausts_retries_raises(api_key, monkeypatch):
    async def _noop_sleep(*_a, **_kw):
        return None
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    with aioresponses() as m:
        for _ in range(4):
            m.get("https://aranet.cloud/api/v1/sensors", status=502, body="bad gateway")
        async with AranetCloudClient(api_key=api_key, max_retries=2) as client:
            with pytest.raises(AranetServerError) as exc_info:
                await client.get_sensors()
        assert exc_info.value.status == 502


# ---------------------------------------------------------------------------
# pagination
# ---------------------------------------------------------------------------


async def test_iter_history_follows_next(api_key):
    """The iterator should chase the `next` URL until empty."""
    page1 = {
        "readings": [
            {"sensor": "1", "metric": "1", "unit": "1", "value": 22.0, "time": "2026-05-19T00:00:00Z"},
            {"sensor": "1", "metric": "1", "unit": "1", "value": 22.1, "time": "2026-05-19T00:05:00Z"},
        ],
        "next": "/api/v1/measurements/history?next=page2token",
    }
    page2 = {
        "readings": [
            {"sensor": "1", "metric": "1", "unit": "1", "value": 22.2, "time": "2026-05-19T00:10:00Z"},
        ],
        "next": "/api/v1/measurements/history?next=page3token",
    }
    page3 = {"readings": []}  # empty terminal page, no next

    with aioresponses() as m:
        m.get(re.compile(r".*/measurements/history\?(?!next=).*"), payload=page1)
        m.get(re.compile(r".*/measurements/history\?next=page2token$"), payload=page2)
        m.get(re.compile(r".*/measurements/history\?next=page3token$"), payload=page3)

        async with AranetCloudClient(api_key=api_key) as client:
            collected = [r async for r in client.iter_measurements_history(hours=1)]
        assert len(collected) == 3
        assert [r.value for r in collected] == [22.0, 22.1, 22.2]


# ---------------------------------------------------------------------------
# session injection
# ---------------------------------------------------------------------------


async def test_injected_session_not_closed_by_client(api_key, sensors_payload):
    """When the caller injects a session, the client must not close it."""
    import aiohttp

    session = aiohttp.ClientSession()
    try:
        with aioresponses() as m:
            m.get("https://aranet.cloud/api/v1/sensors", payload=sensors_payload)
            client = AranetCloudClient(api_key=api_key, session=session)
            await client.get_sensors()
            await client.close()  # should NOT close the session
        assert not session.closed
    finally:
        await session.close()


async def test_empty_api_key_rejected():
    with pytest.raises(ValueError, match="api_key must be non-empty"):
        AranetCloudClient(api_key="")


async def test_injected_session_request_carries_timeout(api_key, sensors_payload):
    """The configured timeout must apply per-request even with an injected
    session (regression: it was only set on transport-owned sessions, so HA
    deployments silently ran with aiohttp's 300 s default)."""
    import aiohttp

    session = aiohttp.ClientSession()
    try:
        with aioresponses() as m:
            m.get("https://aranet.cloud/api/v1/sensors", payload=sensors_payload)
            client = AranetCloudClient(api_key=api_key, session=session, timeout=12.5)
            await client.get_sensors()
        call = next(iter(m.requests.values()))[0]
        assert call.kwargs["timeout"] == aiohttp.ClientTimeout(total=12.5)
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# pagination origin pinning
# ---------------------------------------------------------------------------


async def test_next_url_foreign_host_rejected(api_key):
    """A `next` link pointing at a different host must NOT be followed —
    every request carries the ApiKey header."""
    page1 = {
        "readings": [
            {"sensor": "1", "metric": "1", "unit": "1", "value": 22.0, "time": "2026-05-19T00:00:00Z"},
        ],
        "next": "https://evil.example.com/api/v1/measurements/history?next=tok",
    }
    with aioresponses() as m:
        m.get(re.compile(r"https://aranet\.cloud/api/v1/measurements/history.*"), payload=page1)
        async with AranetCloudClient(api_key=api_key) as client:
            with pytest.raises(AranetError, match="foreign origin"):
                _ = [r async for r in client.iter_measurements_history(hours=1)]


async def test_next_url_http_downgrade_rejected(api_key):
    """Same host but plain http:// is a downgrade — also refused."""
    page1 = {
        "readings": [],
        "next": "http://aranet.cloud/api/v1/measurements/history?next=tok",
    }
    with aioresponses() as m:
        m.get(re.compile(r"https://aranet\.cloud/api/v1/measurements/history.*"), payload=page1)
        async with AranetCloudClient(api_key=api_key) as client:
            with pytest.raises(AranetError, match="foreign origin"):
                _ = [r async for r in client.iter_measurements_history(hours=1)]


async def test_next_url_same_origin_absolute_followed(api_key):
    """Absolute `next` links on the configured origin still work."""
    page1 = {
        "readings": [
            {"sensor": "1", "metric": "1", "unit": "1", "value": 22.0, "time": "2026-05-19T00:00:00Z"},
        ],
        "next": "https://aranet.cloud/api/v1/measurements/history?next=tok2",
    }
    page2 = {
        "readings": [
            {"sensor": "1", "metric": "1", "unit": "1", "value": 22.1, "time": "2026-05-19T00:05:00Z"},
        ],
    }
    with aioresponses() as m:
        m.get(re.compile(r".*/measurements/history\?(?!next=).*"), payload=page1)
        m.get("https://aranet.cloud/api/v1/measurements/history?next=tok2", payload=page2)
        async with AranetCloudClient(api_key=api_key) as client:
            collected = [r async for r in client.iter_measurements_history(hours=1)]
    assert [r.value for r in collected] == [22.0, 22.1]


# ---------------------------------------------------------------------------
# v0.2.1 audit-fix regressions
# ---------------------------------------------------------------------------


async def test_get_bytes_timeout_wrapped_as_connection_error(api_key, monkeypatch):
    """A timeout in the binary download path must surface as
    AranetConnectionError — never a raw TimeoutError escaping the
    documented AranetError hierarchy."""
    async def _noop_sleep(*_a, **_kw):
        return None
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    url = "https://aranet.cloud/api/v1/sensors/sensor/4000001/attachment/att1/file"
    with aioresponses() as m:
        for _ in range(2):
            m.get(url, exception=TimeoutError())
        async with AranetCloudClient(api_key=api_key, max_retries=1) as client:
            with pytest.raises(AranetConnectionError, match="request timed out"):
                await client.download_sensor_attachment("4000001", "att1")


async def test_get_bytes_timeout_then_success_retries(api_key, monkeypatch):
    """A transient timeout on the binary path should be retried, matching
    the JSON path's behaviour."""
    async def _noop_sleep(*_a, **_kw):
        return None
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    url = "https://aranet.cloud/api/v1/sensors/sensor/4000001/attachment/att1/file"
    with aioresponses() as m:
        m.get(url, exception=TimeoutError())
        m.get(url, body=b"\x89PNG-bytes")
        async with AranetCloudClient(api_key=api_key, max_retries=1) as client:
            data = await client.download_sensor_attachment("4000001", "att1")
    assert data == b"\x89PNG-bytes"


async def test_get_bytes_polite_spacing_each_attempt(api_key, monkeypatch):
    """`_respect_min_interval` must run before EVERY attempt of a binary
    download, not just once before the retry loop."""
    async def _noop_sleep(*_a, **_kw):
        return None
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    url = "https://aranet.cloud/api/v1/sensors/sensor/4000001/attachment/att1/file"
    with aioresponses() as m:
        m.get(url, status=503, body="busy")
        m.get(url, body=b"data")
        async with AranetCloudClient(api_key=api_key, max_retries=1) as client:
            calls = 0
            orig = client._transport._respect_min_interval

            async def _counting():
                nonlocal calls
                calls += 1
                await orig()

            monkeypatch.setattr(client._transport, "_respect_min_interval", _counting)
            data = await client.download_sensor_attachment("4000001", "att1")
    assert data == b"data"
    assert calls == 2


async def test_top_level_json_array_raises_server_error(api_key):
    """A 200 whose body is a JSON array (not an object) must raise
    AranetServerError, not leak an AttributeError from `.get(...)`."""
    with aioresponses() as m:
        m.get("https://aranet.cloud/api/v1/sensors", body="[1, 2, 3]")
        async with AranetCloudClient(api_key=api_key) as client:
            with pytest.raises(AranetServerError, match=r"Expected JSON object.*got list"):
                await client.get_sensors()


async def test_rate_limit_retry_after_taken_from_header(api_key):
    """`AranetRateLimitError.retry_after` must come from the `Retry-After`
    header of the final 429 response, not from float()-ing the body."""
    with aioresponses() as m:
        m.get(
            "https://aranet.cloud/api/v1/sensors",
            status=429,
            body="Too Many Requests",
            headers={"Retry-After": "17"},
        )
        async with AranetCloudClient(api_key=api_key, max_retries=0) as client:
            with pytest.raises(AranetRateLimitError) as exc_info:
                await client.get_sensors()
    assert exc_info.value.retry_after == 17.0


async def test_rate_limit_without_header_retry_after_none(api_key):
    """No `Retry-After` header → `retry_after` is None (not a garbage parse
    of the body text)."""
    with aioresponses() as m:
        m.get(
            "https://aranet.cloud/api/v1/sensors",
            status=429,
            body="Too Many Requests",
        )
        async with AranetCloudClient(api_key=api_key, max_retries=0) as client:
            with pytest.raises(AranetRateLimitError) as exc_info:
                await client.get_sensors()
    assert exc_info.value.retry_after is None


# ---------------------------------------------------------------------------
# v0.2.2 hardening regressions
# ---------------------------------------------------------------------------


def test_fmt_dt_converts_aware_datetime_to_utc():
    """A tz-aware non-UTC datetime is converted to UTC before formatting, so
    the API (which reads from/to as UTC) doesn't silently shift the value."""
    from datetime import datetime, timedelta, timezone

    from aranet_cloud.client import _fmt_dt

    pacific = timezone(timedelta(hours=-8))
    assert _fmt_dt(datetime(2026, 5, 19, 12, 0, 0, tzinfo=pacific)) == "2026-05-19T20:00:00"
    # naive passes through unchanged (assumed already UTC)
    assert _fmt_dt(datetime(2026, 5, 19, 12, 0, 0)) == "2026-05-19T12:00:00"
    # strings pass through untouched
    assert _fmt_dt("2026-05-19") == "2026-05-19"


async def test_retry_after_override_is_capped(api_key, monkeypatch):
    """A 429 with an absurd Retry-After must never make the client sleep
    longer than DEFAULT_BACKOFF_CAP — an unbounded server-controlled await
    would silently wedge a polling caller."""
    from aranet_cloud.const import DEFAULT_BACKOFF_CAP

    slept: list[float] = []

    async def _record_sleep(delay, *_a, **_kw):
        slept.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _record_sleep)
    with aioresponses() as m:
        for _ in range(2):
            m.get(
                "https://aranet.cloud/api/v1/sensors",
                status=429,
                body="slow down",
                headers={"Retry-After": "86400"},
            )
        async with AranetCloudClient(api_key=api_key, max_retries=1) as client:
            with pytest.raises(AranetRateLimitError):
                await client.get_sensors()
    assert slept, "expected at least one backoff sleep"
    assert max(slept) <= DEFAULT_BACKOFF_CAP


async def test_400_non_object_error_item_does_not_leak_attributeerror(api_key):
    """A 400 whose error[] holds a bare string (not an object) must still raise
    AranetValidationError — never an AttributeError outside the hierarchy
    (the binary-array sibling of the case fixed in v0.2.1)."""
    with aioresponses() as m:
        m.get(
            "https://aranet.cloud/api/v1/sensors",
            status=400,
            payload={"error": ["just a string, not an object"]},
        )
        async with AranetCloudClient(api_key=api_key) as client:
            with pytest.raises(AranetValidationError) as exc_info:
                await client.get_sensors()
    assert exc_info.value.correlation_id is None


async def test_get_bytes_retries_429(api_key, monkeypatch):
    """The binary download path now retries 429, matching the JSON path."""
    async def _noop_sleep(*_a, **_kw):
        return None

    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    url = "https://aranet.cloud/api/v1/sensors/sensor/4000001/attachment/att1/file"
    with aioresponses() as m:
        m.get(url, status=429, body="slow down", headers={"Retry-After": "1"})
        m.get(url, body=b"PNG-bytes")
        async with AranetCloudClient(api_key=api_key, max_retries=1) as client:
            data = await client.download_sensor_attachment("4000001", "att1")
    assert data == b"PNG-bytes"


async def test_404_raises_not_found(api_key):
    from aranet_cloud import AranetNotFoundError

    with aioresponses() as m:
        m.get("https://aranet.cloud/api/v1/sensors/sensor/999", status=404, body="Not found")
        async with AranetCloudClient(api_key=api_key) as client:
            with pytest.raises(AranetNotFoundError):
                await client.get_sensor("999")


# ---------------------------------------------------------------------------
# coverage for previously-untested endpoints
# ---------------------------------------------------------------------------


async def test_get_telemetry_last(api_key):
    payload = {
        "readings": [
            {"sensor": "4000005", "metric": "61", "unit": "5", "value": -71, "time": "2026-05-19T23:40:55Z"},
            {"sensor": "4000005", "metric": "62", "unit": "6", "value": 2.9, "time": "2026-05-19T23:40:55Z"},
        ],
        "links": {"metric": [{"rel": "61", "name": "RSSI", "href": "/x"}]},
    }
    with aioresponses() as m:
        m.get(re.compile(r"https://aranet\.cloud/api/v1/telemetry/last.*"), payload=payload)
        async with AranetCloudClient(api_key=api_key) as client:
            readings, links = await client.get_telemetry_last(sensor="4000005")
    assert {r.metric for r in readings} == {"61", "62"}
    assert links.name("metric", "61") == "RSSI"


async def test_get_bases_alarms_actual_and_metric(api_key, bases_payload):
    with aioresponses() as m:
        m.get("https://aranet.cloud/api/v1/bases", payload=bases_payload)
        m.get("https://aranet.cloud/api/v1/alarms/actual", payload={"alarms": []})
        m.get(
            "https://aranet.cloud/api/v1/metrics/3",
            payload={"metric": {"id": "3", "name": "CO₂", "kind": "g", "units": []}},
        )
        async with AranetCloudClient(api_key=api_key) as client:
            bases = await client.get_bases()
            alarms = await client.get_alarms_actual()
            metric = await client.get_metric("3")
    assert len(bases) == 1
    assert alarms == []
    assert metric.id == "3"
    assert metric.is_gauge
