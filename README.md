# aranet-cloud

Async Python client for the [Aranet Cloud](https://aranet.cloud/) REST API.

Wraps every endpoint in the public Aranet Cloud OpenAPI 3.0 spec (27 GETs,
read-only) and returns typed dataclass models. Designed primarily as the
backing library for the [aranet-cloud-homeassistant](https://github.com/jasonjhofmann/aranet-cloud-homeassistant)
HACS integration, but usable as a standalone Python client.

> **Status:** Pre-release (0.1.x). API surface may shift as the HA
> integration drives requirements. The OpenAPI mapping is stable.

## Install

```bash
pip install aranet-cloud
```

Python 3.11+ required. Single runtime dependency: `aiohttp`.

## Quick start

```python
import asyncio
from aranet_cloud import AranetCloudClient

async def main() -> None:
    async with AranetCloudClient(api_key="...") as client:
        sensors = await client.get_sensors()
        for s in sensors:
            print(f"{s.serial}  {s.name} ({s.type})")

        readings, links = await client.get_measurements_last()
        for r in readings:
            metric_name = links.name("metric", r.metric) or r.metric
            unit_name = links.name("unit", r.unit) or r.unit
            print(f"  {r.sensor}  {metric_name}: {r.value} {unit_name}")

asyncio.run(main())
```

## Authentication

The Aranet Cloud API uses a single header — `ApiKey: <your-key>`. No
OAuth, no token refresh. Get your key from the Aranet Cloud dashboard
under Account → API.

## What's covered

All 27 GET endpoints in the public OpenAPI spec:

- **Sensors** — list, detail, sensor types, attachments
- **Measurements** — last + paginated history (gauge metrics: T, RH, CO₂, P, soil...)
- **Telemetry** — last + paginated history (RSSI, battery, base status)
- **Bases** — list + per-base detail (incl. enterprise config)
- **Alarms** — actual + historical, rules
- **Assets / Tags** — virtual containers + organisation
- **Metric / Unit catalog** — full lookup tables

See [`docs/architecture.md`](docs/architecture.md) for the full API
reference, edge cases, and design notes.

## Design

- Async-first (`aiohttp`). Use as an async context manager or inject
  an existing `ClientSession` (the HA-friendly pattern).
- Typed: every response shape modelled as a dataclass with `from_dict`
  that ignores unknown fields (forward-compatible with new server fields).
- Pagination hidden — `iter_measurements_history()` is an async
  generator that follows `next` tokens transparently.
- Exception hierarchy distinguishes auth (401), validation (400 with
  correlation ID), rate-limit (429), server (5xx), and network errors.
- Retry/backoff on 5xx, 429, and transient network failures.
- Polite-spacing floor between successive requests (no documented
  rate limit but we don't hammer).

## Development

```bash
git clone https://github.com/jasonjhofmann/aranet-cloud
cd aranet-cloud
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
mypy src
```

## License

Apache 2.0
