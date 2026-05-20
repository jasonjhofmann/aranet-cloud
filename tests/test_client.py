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
        assert any(s.name == "Primary Bedroom" for s in sensors)


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
            "https://aranet.cloud/api/v1/sensors?base=358151002573",
            payload={"sensors": []},
        )
        async with AranetCloudClient(api_key=api_key) as client:
            sensors = await client.get_sensors(base="358151002573")
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
