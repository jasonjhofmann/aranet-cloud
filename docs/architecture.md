# Aranet Cloud — API reference + library architecture

Canonical reference for the `aranet-cloud` Python library and the
`aranet-cloud-homeassistant` integration that depends on it.

Source of truth: `docs/openapi.json` (39 KB, OpenAPI 3.0.3) + the live-tested
findings recorded below.

---

## API at a glance

- **Base URL:** `https://aranet.cloud`
- **All endpoints:** under `/api/v1/`, all `GET`, all read-only (27 total)
- **Authentication:** single header `ApiKey: <key>` (no OAuth, no refresh, no
  expiry signalled by the server — assume keys are long-lived until rotated by
  the user)
- **OpenAPI spec (raw JSON):** publicly accessible at
  `https://aranet.cloud/api/openapi.json` (the rendered Swagger UI at
  `/openapi/` is gated and returns 403 — that is not an outage, the raw spec
  is the canonical source)
- **No documented rate limit.** 20-request burst in 12.6 s (1.6 req/sec) ran
  through cleanly. Default lib behaviour: polite, ≥ 1 s between requests,
  honour 429 with exponential backoff if it ever appears
- **TLS:** Cloudflare-fronted, current cert (issued April 2026)

---

## Auth model

Single `apiKey` security scheme:

```yaml
ApiKey:
  type: apiKey
  in:   header
  name: ApiKey         # ← literal header name, NOT "Authorization"
```

Auth error responses are **plain text**, not JSON:

| Status | Body | Cause |
|---|---|---|
| 401 | `Invalid ApiKey` | Header present, value wrong/revoked |
| 401 | `Not Authorized` | Header missing |

Validation errors (e.g. bad date) ARE JSON:

```json
{"error":[{"message":"Invalid time parameter not-a-date","id":"d86fu2jf9lnc739nt3n0"}]}
```

The `id` field is an opaque correlation token — log it on errors so users can
ask Aranet support to look up server-side traces.

A 200 with `{}` body can come back from queries with no matching data
(e.g. `?sensor=<bogus_id>` returns `200 {}`, not 404). Treat empty/missing
top-level keys (`readings`, `sensors`, `bases`, etc.) as "no data" — not an
error.

---

## Endpoint inventory (27 GETs)

Grouped by domain. `*` = path param. All return JSON unless noted.

### Sensors (the workhorse — gauge measurements)

| Endpoint | Purpose | Response wrapper key |
|---|---|---|
| `GET /api/v1/sensors[?base=<csv>]` | List all sensors (optional base-station filter) | `sensors[]` |
| `GET /api/v1/sensors/sensor/{*}` | Single-sensor detail incl. files, pairing, probes, skills | `sensor` |
| `GET /api/v1/sensors/types` | Catalog of every sensor type the cloud knows (53 in mid-2026) | `sensorTypes[]` |
| `GET /api/v1/sensors/types/type/{*}` | Per-type detail (incl. `isVirtual`, `conversionType`, icon) | `sensorType` |
| `GET /api/v1/sensors/sensor/{*}/attachment/{*}` | Attachment metadata | (not yet probed — likely `attachment`) |
| `GET /api/v1/sensors/sensor/{*}/attachment/{*}/file` | Binary file download | `application/octet-stream` |
| `GET /api/v1/sensors/sensor/{*}/attachment/{*}/thumbnail` | Image thumbnail | `image/*` |

### Measurements (gauge readings — the data plane)

| Endpoint | Purpose | Response key |
|---|---|---|
| `GET /api/v1/measurements/last[?sensor=&asset=&point=&metric=&unit=&links=]` | Latest reading per sensor × metric | `readings[]` |
| `GET /api/v1/measurements/history[?<same>&from=&to=&seconds/minutes/hours/days=&next=&limit=]` | Historical, paginated, max 7 d unfiltered / 6 mo filtered | `readings[]`, `next` |

**Pagination:** `next` in the response body is a **fully-formed relative URL**
ready to GET (preserves all original query params + an opaque `next` token).
Just follow until `next` is absent or `readings` is empty. The doc warns that
the last page may be empty due to optimisation.

**Time params:** mutually exclusive forms — either `from`+`to` (ISO 8601
UTC dates, `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM`) OR one of `seconds`/`minutes`/
`hours`/`days` for a relative window.

**Default window:**

| Filter set | Default | Max |
|---|---|---|
| No sensor/asset/point filter | last 24 h | 7 d |
| `sensor=...` set | last 7 d | 6 months |
| `asset=...` or `point=...` set | last 24 h | 6 months |

**Alternate response format:** `Accept: application/senml+json` returns IETF
SenML (RFC 8428) with sensor URNs like `aranet:4000005:co2` and base time
`bt` (epoch seconds). Units differ from the regular JSON (`Cel` vs `°C`, `/`
vs `ppm`, CO₂ as fraction `0.000757` vs `757`). **Lib should support both,
default to the regular JSON; HA integration uses regular only.**

### Telemetry (sensor-about-sensor — RSSI, battery)

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/telemetry/last[?sensor=&metric=&links=]` | Latest battery/RSSI per sensor |
| `GET /api/v1/telemetry/history[?<measurements-like-params>]` | Historical telemetry, paginated |

Same `readings[]` shape as `/measurements/*`, but only `kind=t` metrics
(currently 61=RSSI, 62=battery, 81=base-station-status). **Critical for HA
integration:** poll both `/measurements/last` AND `/telemetry/last` to get
the full per-sensor state — they're disjoint metric sets.

### Bases (sensor hubs)

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/bases` | List base stations (gateway hardware) |
| `GET /api/v1/bases/base/{*}` | Base detail incl. firmware, product/board codes, region, config (wifi, modbus, BACnet, MQTT, NTP, snmp, LTE, GSM, ethernet) |

Base `config` may be `{}` for non-enterprise deployments. The schema reserves
keys for full network config — useful for the HA `diagnostics` platform but
not for entity state.

### Alarms

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/alarms/actual` | Currently active alarms — drives `binary_sensor` |
| `GET /api/v1/alarms/history?from=&to=` | Historical alarm fires |
| `GET /api/v1/alarms/rules` | All alarm rules incl. built-ins (Low battery, Base station offline) |
| `GET /api/v1/alarms/rules/rule/{*}` | Rule detail |

`AlarmInfo` carries: id, sensor, metric, rule, severity, threshold, value, worst,
alarmed/resolved timestamps, note. Rich enough to attribute alarms to specific
sensor/metric pairs.

### Organisation (assets, tags)

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/assets` | Virtual containers (e.g. "Greenhouse Zone A") with `points` (measurement points), `tags`, files |
| `GET /api/v1/assets/asset/{*}` | Asset detail |
| `GET /api/v1/assets/asset/{*}/attachment/{*}[/file\|/thumbnail]` | Files attached to asset |
| `GET /api/v1/tags` | All tags (id, name, notes, type) |
| `GET /api/v1/tags/tag/{*}` | Tag detail |

**HA mapping idea:** map Aranet `tags` to HA labels and `assets` to HA areas
(if `assets[].location` is meaningful enough). For users (like ours) with no
assets/tags configured, both lists are empty — handle that gracefully.

### Metric / unit catalog (static-ish lookup tables)

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/metrics` | All metric definitions (id, name, kind=`g`/`t`, available units) |
| `GET /api/v1/metrics/{*}` | Single metric detail (same shape) |
| `GET /api/v1/units/unit/{*}` | Unit detail (id, name, **precision** = decimal places) |

The full metric/unit catalog should be fetched ONCE at startup, then cached
in memory. Drives entity-state formatting (precision, unit-of-measurement).

---

## Metric catalogue (as of probe — 14 metrics live in this account)

| id | name | kind | preferred unit | HA `device_class` |
|---|---|---|---|---|
| 1 | Temperature | gauge | °C / °F | `temperature` |
| 2 | Humidity | gauge | % / %RH | `humidity` |
| 3 | CO₂ | gauge | ppm | `carbon_dioxide` |
| 4 | Atmospheric Pressure | gauge | hPa / mmHg / inHg / Pa / atm / bar / psi | `atmospheric_pressure` |
| 8 | Volumetric Water Content | gauge | % | `moisture` (HA) or `humidity` |
| 9 | Soil Dielectric Permittivity | gauge | (unitless) | — (custom) |
| 10 | Soil Electrical Conductivity | gauge | S/m / mS/cm | — (custom) |
| 11 | Pore Electrical Conductivity | gauge | S/m / mS/cm | — (custom) |
| 24 | Fraction | gauge | — / / | — |
| 28 | Vapour-Pressure Deficit | gauge | Pa / kPa / bar / hPa / psi | `pressure` |
| 29 | Day Light Integral | gauge | mol/m²/d / µmol/m²/d | — (custom) |
| 61 | RSSI | telemetry | dBm / dBW | `signal_strength` |
| 62 | Battery voltage | telemetry | % / V | `battery` |
| 81 | Base station status | telemetry | (unitless) | — (binary_sensor) |

Soil metrics (8–11, 28, 29) don't all have HA device classes — we'll need
custom `unit_of_measurement` + `state_class: measurement` and let HA's
history/statistics work generically. Document this for users so soil-sensor
charts behave nicely.

---

## Sensor types (53 known in catalogue)

Examples relevant to this account:

| type | name | notes |
|---|---|---|
| S4V1 | Aranet4 | 4-in-1 air quality (T, RH, CO₂, P) |
| S4V5 | Aranet2 | Lower-tier air quality |
| S1V16 | (one of the legacy types) | 2-metric variant |
| S6V4 | Soil moisture sensor | basic 1-probe soil + temp |
| S6V1 | Soil VWC, EC and T sensor | Delta-T WET150 — research-grade 4-probe |
| S6V7 | IR Plant Temperature sensor | |
| S5V1 / S5V2 | 0–10 VDC / 4–20 mA transmitter | Industrial input bridges |

`isVirtual: true` types (Average, Dew point, Day Light Integral, Expert) are
cloud-computed pseudo-sensors. They show up in the sensor list just like
physical sensors and should be mapped 1:1 to HA devices, with a label/note
indicating "virtual" for clarity.

**Forward compatibility:** new physical sensor types ship as firmware updates
to bases. The integration must not hard-code a closed set — unknown sensor
types should still surface as HA devices with generic naming (`type=Sxxxx`)
and whatever metrics the cloud reports for them.

---

## Common response shape

Most list responses follow the pattern:

```json
{
  "<entity_key_plural>": [ … ],
  "links": {
    "<rel>": [ { "rel": "<id>", "name": "<display>", "href": "<path>" } ]
  },
  "self":  "<canonical URL of this query>",
  "next":  "<URL of next page>",
  "error": [ { "message": "...", "id": "..." } ]
}
```

`links` is a side-channel of human-readable names for the IDs referenced in
the data array — saves a second round-trip for display. The lib should
optionally expose these (e.g. `Reading.metric_name = links.metric[reading.metric].name`).

---

## Library architecture (`aranet-cloud` on PyPI)

```
src/aranet_cloud/
├── __init__.py            # public API surface (re-exports)
├── client.py              # AranetCloudClient — single async class, one method per endpoint
├── models.py              # dataclasses for all 48 response schemas
├── exceptions.py          # AranetError (base), AranetAuthError (401),
                           # AranetValidationError (400), AranetRateLimitError (429),
                           # AranetServerError (5xx), AranetConnectionError
├── enums.py               # MetricKind, SeverityLevel, etc.
├── const.py               # BASE_URL, endpoint path templates, ApiKey header name
├── _http.py               # aiohttp session mgmt, request hook, retry/backoff
├── _senml.py              # optional senml+json decoder
└── py.typed               # PEP 561 marker
```

### Design principles

1. **Async-first.** Single `AranetCloudClient(api_key, *, session=None, base_url=None, timeout=30)` — pass-in session for HA's shared session injection, or auto-create. Async context manager (`async with client:`).
2. **One method per endpoint**, named after the path: `get_sensors()`, `get_sensor(sensor_id)`, `get_measurements_last(*, sensor=None, ...)`, `iter_measurements_history(...)` (async iterator that follows `next`).
3. **Typed everything.** Pure stdlib dataclasses with explicit `from_dict` classmethods (Pydantic was considered and rejected — adds a heavyweight runtime dependency for no functional gain at this scale). `from __future__ import annotations` throughout. PEP 561 `py.typed` ships.
4. **No HA dependency.** Pure Python + `aiohttp`. Lib is reusable in non-HA scripts (CLI utilities, Savant ingestion, dashboards).
5. **Graceful unknown-field handling.** When Aranet adds new fields server-side, the lib must NOT crash — every `from_dict` ignores unknown keys. The integration may want to surface unknown fields as diagnostics.
6. **Logging.** `logging.getLogger("aranet_cloud")` for the lib; HA's `_LOGGER = logging.getLogger(__name__)` in the integration. Lib logs at DEBUG for every request (method, path, status, elapsed) and at WARNING for retried/failed requests. **Never log the API key.**
7. **Retry policy.** On 5xx / `aiohttp.ClientError` / `asyncio.TimeoutError`: exponential backoff (1s, 2s, 4s, 8s), max 3 retries. On 401: raise immediately. On 400: raise immediately. On 429 (if it ever appears): honour `Retry-After` if present; else cap-aware exponential.
8. **Pagination.** `iter_measurements_history()` and `iter_telemetry_history()` are async generators yielding `Reading` objects one by one. The user never has to think about `next` tokens.
9. **Catalog caching helper.** *(Reserved for a later version; not in v0.1.0.)* The HA integration currently re-fetches the small catalog endpoints alongside measurements on every coordinator cycle — they're cheap and the simplicity outweighs the optimisation.

### Method surface (sketch)

```python
class AranetCloudClient:
    async def get_sensors(self, *, base: list[str] | None = None) -> list[Sensor]: ...
    async def get_sensor(self, sensor_id: int) -> Sensor: ...
    async def get_sensor_types(self) -> list[SensorType]: ...
    async def get_sensor_type(self, type_id: str) -> SensorType: ...

    async def get_bases(self) -> list[Base]: ...
    async def get_base(self, base_id: str) -> Base: ...

    async def get_measurements_last(self, *, sensor=None, asset=None, point=None,
                                    metric=None, unit=None) -> list[Reading]: ...
    async def iter_measurements_history(self, *, sensor=None, ..., from_=None, to=None,
                                        seconds=None, minutes=None, hours=None, days=None,
                                        limit=None) -> AsyncIterator[Reading]: ...

    async def get_telemetry_last(self, *, sensor=None, metric=None) -> list[Reading]: ...
    async def iter_telemetry_history(self, **kwargs) -> AsyncIterator[Reading]: ...

    async def get_alarms_actual(self) -> list[Alarm]: ...
    async def get_alarms_history(self, *, from_=None, to=None) -> list[Alarm]: ...
    async def get_alarm_rules(self) -> list[AlarmRule]: ...
    async def get_alarm_rule(self, rule_id: int) -> AlarmRule: ...

    async def get_assets(self) -> list[Asset]: ...
    async def get_asset(self, asset_id: int) -> Asset: ...

    async def get_tags(self) -> list[Tag]: ...
    async def get_tag(self, tag_id: str) -> Tag: ...

    async def get_metrics(self) -> list[Metric]: ...
    async def get_metric(self, metric_id: int) -> Metric: ...
    async def get_unit(self, unit_id: str) -> Unit: ...

    async def download_attachment(self, *, sensor_id=None, asset_id=None,
                                  attachment_id: str, thumbnail: bool = False) -> bytes: ...
```

---

## HA integration architecture (`aranet-cloud-homeassistant`)

```
custom_components/aranet_cloud/
├── __init__.py             # async_setup_entry, async_unload_entry
├── config_flow.py          # UI: API key + base URL override + options
├── coordinator.py          # DataUpdateCoordinator subclasses (one per cadence)
├── const.py
├── diagnostics.py          # redacted snapshot for "Download diagnostics"
├── repairs.py              # actionable issues (revoked key, etc.)
├── sensor.py               # SensorEntity per (sensor × metric)
├── binary_sensor.py        # AlarmEntity from /alarms/actual
├── manifest.json           # version, deps (["aranet-cloud>=0.1"]), iot_class="cloud_polling"
├── strings.json            # English source for translations
├── translations/en.json
└── services.yaml           # e.g. aranet_cloud.refresh, aranet_cloud.fetch_history
```

### Two coordinators (different cadences)

1. **MeasurementsCoordinator** — fast loop (default 60 s, configurable 30–600 s).
   Polls `measurements/last` + `telemetry/last` + `alarms/actual`. Drives the
   per-sensor entities + binary_sensors.
2. **CatalogCoordinator** — slow loop (default 1 h, configurable). Polls
   `/sensors`, `/sensors/types`, `/bases`, `/metrics`, `/units`, `/tags`,
   `/assets`, `/alarms/rules`. Drives device discovery + metadata refresh.
   This is the coordinator that notices "user added a new sensor in the Aranet
   app" without requiring an HA restart.

Entities subscribe to whichever coordinator they need (most sensors → fast;
diagnostics → slow).

### Entity-id stability

Use `sensor.sensorId` (the 5-char hex code like `A0005`, NOT the numeric `id`)
in the HA `unique_id`. The numeric `id` is a cloud-side primary key that
*could* change if Aranet ever re-keys; the hex `sensorId` is the device's
permanent identity (printed on the sticker).

`unique_id` shape: `aranet_cloud_{sensorId}_{metric_id}` →
`aranet_cloud_A0005_3` for Bedroom CO₂. Stable across renames,
re-pairings, and cloud-side ID churn.

### Device hierarchy

```
Aranet account (one "via" device per integration entry)
└── Base station(s) (one device per Aranet base)
    └── Sensor(s) (one device per Aranet sensor — paired via base)
        └── Entity(s) (one per metric)
```

Base ↔ sensor link comes from `sensor.bases[]` + `sensor.pairing[]`. If a
sensor is paired with multiple bases (multi-base setups), pick the
most-recently-paired as the `via_device`.

### Diagnostics + repairs

- **Diagnostics:** dumps the entire coordinator state (raw API responses,
  sanitised) — sensors, bases, measurements_last, telemetry_last, alarms_actual,
  catalog. **Redact `api_key`** at the top of the file. Useful for any bug
  report; copy/paste into a GH issue.
- **Repairs flow:** on persistent 401, raise a repair issue with a CTA to
  re-enter the API key. On unknown sensor types appearing for the first time,
  raise an informational issue with a link to file a GitHub issue.

---

## Open questions / parking lot

- **Async iteration over hours of history is slow.** A user requesting last
  6 months of data could blow through hundreds of pages. Should the lib
  enforce a hard cap, or trust the caller? **Decision:** lib trusts, but
  documents loudly. HA integration *will not* expose unbounded history fetches
  — only fixed windows via services.
- **Long-term statistics import.** HA supports `async_add_external_statistics`
  for back-filling historical data. Tempting to do this for users who join
  with months of cloud history. **Decision for v1:** defer; out of MVP.
- **Attachments.** S4V1 sensors auto-attach a thumbnail (e.g.
  `"Bedroom.png"` on sensor 4000005). Could surface as an HA `image`
  entity. **Decision for v1:** stretch; do if cheap.
- **Multi-account.** A user with multiple Aranet API keys (e.g. personal +
  business). HA config flow can accept multiple entries — each gets its own
  coordinator. **Decision:** support via standard HA multi-entry pattern; no
  special handling.
- **Account-level identity in HA.** `manifest.json` needs a stable identifier
  for the "Aranet account" device. The API doesn't expose an account ID
  directly — use a hash of the API key (don't store the key in the device
  registry, but a stable hash is fine).

---

## Verified behaviours (live-probed 2026-05-19)

These are observations against the live API on the user's account, not
documented anywhere except the OpenAPI spec — captured here so the lib's
tests can assert against them.

- `?sensor=<nonexistent>` returns `200 {}` (empty top-level object, NOT 404)
- `/measurements/history?limit=5` returns 5 readings AND a `next` URL
- `next` is a relative URL starting with `/api/v1/...` (just append to base)
- `Accept: application/senml+json` actually flips the response format
  (returns `application/senml+json` content-type with sensor-URN-keyed array)
- Auth errors are plain text bodies, not JSON
- Validation errors are JSON with `error[].id` correlation token
- `lastSeen` on bases can be `null` (this user's case)
- Base `config` is `{}` for consumer accounts (non-enterprise tier)
- 20 sequential requests in 12.6 s succeed without 429 (no observable
  rate limit at this tier — but lib still implements polite spacing)
