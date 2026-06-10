# Changelog

All notable changes to **aranet-cloud** are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning is [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-06-10

Hardening release from a code audit. One **breaking** change: numeric
measurement values are now ``float | None``.

### Changed

- **Breaking:** `Reading.value`, `Alarm.value`, and `Alarm.worst` are now
  `float | None`. A `null` (or unparseable) value from the API surfaces as
  `None` instead of being silently coerced to `0.0` — missing data can no
  longer masquerade as a genuine zero reading (e.g. 0 ppm CO₂).
- Sample payloads in `docs/` and the test fixtures are now fully synthetic:
  all real sensor serials, cloud IDs, the base-station ID/name, and room
  names have been replaced with fabricated equivalents. (The originals
  remain in git history prior to this release.)

### Fixed

- The configured request `timeout` (default 30 s) is now applied to every
  request, including when an `aiohttp.ClientSession` is injected by the
  caller. Previously it only took effect on transport-owned sessions, so
  Home Assistant-style deployments silently ran with aiohttp's 300 s
  default.

### Security

- Server-supplied pagination `next` links are now only followed when their
  origin (scheme + host + port) matches the configured `base_url`. An
  absolute URL pointing at a foreign host — or an https→http downgrade —
  raises `AranetError` instead of being requested with the `ApiKey` header
  attached.

## [0.1.0] — 2026-05-19

Initial release. Async client for every endpoint in the Aranet Cloud
OpenAPI 3.0 spec (27 GETs, read-only), typed dataclass models, hidden
pagination, full exception hierarchy.

### Added

- `AranetCloudClient` — async client with one method per documented
  endpoint:
  - Sensors: `get_sensors`, `get_sensor`, `get_sensor_types`,
    `get_sensor_type`
  - Measurements: `get_measurements_last`, `iter_measurements_history`
  - Telemetry: `get_telemetry_last`, `iter_telemetry_history`
  - Bases: `get_bases`, `get_base`
  - Alarms: `get_alarms_actual`, `get_alarms_history`, `get_alarm_rules`,
    `get_alarm_rule`
  - Assets: `get_assets`, `get_asset`
  - Tags: `get_tags`, `get_tag`
  - Catalog: `get_metrics`, `get_metric`, `get_unit`
  - Attachments: `download_sensor_attachment`, `download_asset_attachment`
- 21 dataclasses covering the response schemas: `Sensor`, `SensorType`,
  `Skill`, `Pairing`, `Probe`, `FileRef`, `Reading`, `Base`, `Alarm`,
  `AlarmRule`, `Metric`, `Unit`, `Tag`, `TagType`, `Asset`,
  `MeasurementPoint`, `MeasurementPointSkill`, `AssetSensor`, `Link`,
  `Links`, `ErrorDetail`. Each provides a `from_dict` classmethod that
  silently ignores unknown fields (forward-compatible with future API
  additions).
- Exception hierarchy: `AranetError` (base), `AranetAuthError` (401,
  plain-text body), `AranetValidationError` (400, with
  `correlation_id`), `AranetRateLimitError` (429, with `retry_after`),
  `AranetServerError` (5xx after retries), `AranetConnectionError`
  (network/timeout), `AranetNotFoundError` (404).
- Async-iterator pagination engine — `iter_measurements_history` and
  `iter_telemetry_history` follow the `next` URL transparently and yield
  `Reading` objects one at a time.
- Exponential-backoff retry on 5xx, 429, and transient `aiohttp.ClientError`
  with a 30 s cap; honours server-supplied `Retry-After` on 429.
- Polite-spacing floor (250 ms) between successive requests.
- Optional session injection — pass an existing `aiohttp.ClientSession`
  to share with the rest of a host application (the HA-friendly pattern);
  the lib auto-creates and owns its session otherwise.
- `__all__` exports a curated public surface; `py.typed` marker for PEP
  561 type checkers.
- 23 unit + integration tests against `aioresponses` covering happy
  paths, header injection, error classification, 5xx retry, 400
  correlation-ID extraction, pagination, and injected-session
  non-closure.
- Documentation: full `docs/architecture.md` API reference, sample
  response fixtures from a real account.

### Notes

- Live-verified end-to-end against the production Aranet Cloud API on
  2026-05-19 (13 sensors across all four sensor type families on the
  test account).
- Build tooling: `ruff` (lint), `mypy --strict` (types), `pytest` +
  `pytest-asyncio` (tests), `hatchling` (wheel/sdist).

[Unreleased]: https://github.com/jasonjhofmann/aranet-cloud/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jasonjhofmann/aranet-cloud/releases/tag/v0.1.0
