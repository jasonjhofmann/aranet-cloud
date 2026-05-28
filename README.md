# aranet-cloud

[![python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![license](https://img.shields.io/badge/license-Apache_2.0-green.svg)](LICENSE)
[![release](https://img.shields.io/github/v/release/jasonjhofmann/aranet-cloud?label=release&color=blue)](https://github.com/jasonjhofmann/aranet-cloud/releases) [![pypi](https://img.shields.io/pypi/v/aranet-cloud?label=PyPI&color=blue)](https://pypi.org/project/aranet-cloud/)

Async Python client for the [Aranet Cloud](https://aranet.cloud/) REST API.

Wraps every endpoint in the public Aranet Cloud OpenAPI 3.0 spec — 27
read-only `GET` endpoints — and returns typed dataclass models. Designed
primarily as the backing library for the
[`aranet-cloud-homeassistant`](https://github.com/jasonjhofmann/aranet-cloud-homeassistant)
HACS integration, but usable as a standalone Python client.

> **Status:** Pre-release (0.1.x). The OpenAPI mapping is stable; the
> public Python surface may evolve as the HA integration drives
> requirements. Pin to a minor version in production.

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
        # List every sensor on your account
        sensors = await client.get_sensors()
        for s in sensors:
            print(f"  {s.serial}  {s.name:<30s}  type={s.type}")

        # Latest reading per (sensor × metric), with name resolution
        readings, links = await client.get_measurements_last()
        for r in readings:
            metric = links.name("metric", r.metric) or r.metric
            unit   = links.name("unit",   r.unit)   or r.unit
            print(f"  {r.sensor:>10s}  {metric:>22s}: {r.value} {unit}")

asyncio.run(main())
```

Output against a typical home/garden account:

```
  02D0C  Primary Bedroom               type=S4V1
  02E2C  Kitchen                       type=S4V1
  ...

  4205836           Temperature: 72.5 °F
  4205836              Humidity: 30 %
  4205836                    CO₂: 757 ppm
  4205836   Atmospheric Pressure: 697.9 mmHg
  ...
```

## Authentication

The Aranet Cloud API uses a single header — `ApiKey: <your-key>`. No
OAuth, no token refresh. Generate a key from your Aranet Cloud dashboard
under **Account → API**.

```python
AranetCloudClient(api_key="vku...")
```

## What's covered

All 27 GET endpoints in the public OpenAPI spec:

| Domain | Methods |
|---|---|
| **Sensors** | `get_sensors`, `get_sensor`, `get_sensor_types`, `get_sensor_type` |
| **Measurements** | `get_measurements_last`, `iter_measurements_history` (paginated) |
| **Telemetry** | `get_telemetry_last`, `iter_telemetry_history` (paginated) |
| **Bases** | `get_bases`, `get_base` |
| **Alarms** | `get_alarms_actual`, `get_alarms_history`, `get_alarm_rules`, `get_alarm_rule` |
| **Assets** | `get_assets`, `get_asset` |
| **Tags** | `get_tags`, `get_tag` |
| **Catalog** | `get_metrics`, `get_metric`, `get_unit` |
| **Attachments** | `download_sensor_attachment`, `download_asset_attachment` |

See [`docs/architecture.md`](docs/architecture.md) for the full API
reference, edge cases discovered during live probing, and design notes.

## Pagination

History endpoints are paginated by the server. The library hides the
mechanics via async iterators:

```python
async for reading in client.iter_measurements_history(sensor="4205836", hours=24):
    print(reading.time, reading.value)
```

The iterator follows the `next` token transparently until the server
returns no more data. **Mind the time windows** — `/measurements/history`
without a sensor filter caps at 7 days; with a sensor filter it caps at
6 months.

## Exception hierarchy

```
AranetError                       ← base; catch this for a blanket handler
├── AranetConnectionError         ← network, timeout, TLS, DNS
├── AranetAuthError               ← 401 (key wrong/missing/revoked) - NOT transient
├── AranetValidationError         ← 400 (carries correlation_id from API)
├── AranetRateLimitError          ← 429 (with retry_after if present)
├── AranetServerError             ← 5xx after exhausted retries
└── AranetNotFoundError           ← 404 (rare; API often returns 200 {} instead)
```

Auth errors deserve special handling — the Aranet API returns 401 as
**plain text** (not JSON), so `AranetAuthError` doesn't carry a
correlation ID. Validation errors are JSON with `error[].id` correlation
tokens, preserved on `AranetValidationError.correlation_id` for support
escalations.

## Design

- **Async-first** (`aiohttp`). Use as an async context manager (auto
  session) or inject an existing `ClientSession` — the HA-friendly
  pattern.
- **Typed**: every response shape modelled as a dataclass with
  `from_dict` that ignores unknown fields, forward-compatible with new
  server fields.
- **Pagination hidden**: `iter_*_history()` async generators follow
  `next` tokens transparently.
- **Retry/backoff** on 5xx, 429, and transient network failures.
  Exponential backoff `(1s, 2s, 4s, 8s)` capped at 30 s; max 3 retries
  by default.
- **Polite-spacing** floor (250 ms) between successive requests. The
  Aranet API has no documented rate limit, but we don't hammer.
- **Never logs the API key.** Debug logs cover request method, path,
  status, and body size; the key is in headers only.

## Standalone usage outside Home Assistant

The library has no HA dependencies and is fine to use in standalone
Python scripts, FastAPI services, data-ingestion pipelines, etc.:

```python
async with AranetCloudClient(api_key="...") as client:
    # Pull 24 hours of CO₂ readings for a single sensor
    readings = [
        r async for r in client.iter_measurements_history(
            sensor="4205836", metric="3", hours=24,
        )
    ]
    print(f"got {len(readings)} CO₂ samples")
```

## Development

```bash
git clone https://github.com/jasonjhofmann/aranet-cloud
cd aranet-cloud
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest               # 23 tests, ~0.7s
ruff check .         # lint
mypy src             # type-check (strict)
python -m build      # build wheel + sdist
```

## License

Apache 2.0
