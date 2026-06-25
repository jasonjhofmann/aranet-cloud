# Changelog

All notable changes to **aranet-cloud** are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning is [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.2] — 2026-06-25

Hardening, robustness, and tooling release from a full-repo review. No
breaking changes; all public signatures and types are unchanged.

### Added

- **CI gate.** `.github/workflows/ci.yml` runs `ruff`, `mypy --strict`, and
  the test suite on Python 3.11 / 3.12 / 3.13 for every push and PR.
  Previously no workflow exercised the test/lint/type gate that
  `CONTRIBUTING.md` and `README.md` already pointed at.
- `.github/dependabot.yml` keeps GitHub Actions and Python dependencies
  current (weekly).
- Test coverage for previously-untested paths — `telemetry/last`, `bases`,
  `alarms/actual`, single-metric, `404` → `AranetNotFoundError` — plus a
  regression test for every fix below. 50 tests total (up from 39), now green
  on a fresh `pip install -e ".[dev]"`.

### Fixed

- **Unbounded backoff on `Retry-After`.** A `429` carrying a large (or
  hostile) `Retry-After` is now clamped to `DEFAULT_BACKOFF_CAP` (30 s) on the
  override path too, not only the exponential path. Previously a value like
  `Retry-After: 86400` made the client `await asyncio.sleep` for ~24 h per
  retry, silently wedging a polling caller (e.g. an HA
  `DataUpdateCoordinator`).
- **`from_dict` no longer crashes on malformed integer fields.** `_as_int`
  (and `Skill.probes` parsing) coerce defensively like `_as_float_or_none` —
  returning `0` / skipping the entry instead of raising a bare
  `ValueError`/`TypeError` outside the `AranetError` hierarchy — honouring the
  documented "tolerate unexpected server data, never crash" contract.
- **`_as_float_or_none` rejects non-finite values.** `inf`/`nan` (including the
  string forms `float()` accepts) now map to `None`, so a bogus reading can't
  masquerade as real data — the same no-masquerade guarantee already applied
  to `null`.
- **400 error parsing hardened.** A `400` whose `error[]` array holds a
  non-object first item (e.g. a bare string) still raises
  `AranetValidationError` instead of leaking an `AttributeError` — the
  remaining sibling of the top-level-array case fixed in 0.2.1.
- **Timezone-aware datetimes are converted to UTC** before being sent as
  `from`/`to`. Previously a tz-aware non-UTC datetime had its wall-clock
  digits reinterpreted as UTC (a silent multi-hour shift). Naive datetimes are
  still assumed to be UTC.
- **Binary attachment downloads reached parity with the JSON path:** they now
  retry `429`, emit the same per-request DEBUG line, and log a WARNING on
  network-error retries.

### Security

- Raised the `aiohttp` dependency floor from `>=3.9` to `>=3.10.11`.
  3.10.11 fixes **CVE-2024-52304** (GHSA-8495-4g3g-x7pr): the pure-Python
  HTTP parser parsed newlines in chunk extensions incorrectly, allowing an
  HTTP request-smuggling attack to bypass firewall/proxy protections when
  the C extensions are unavailable (or `AIOHTTP_NO_EXTENSIONS` is set).
  This is a transitive hardening only — `aranet-cloud` is a client and does
  not run the affected server parser, but pinning the floor keeps any
  installation off the vulnerable releases.
- **JSON API requests no longer follow HTTP redirects** (`allow_redirects=False`).
  The documented endpoints never redirect; following a server-supplied 30x
  would re-send the `ApiKey` header to the redirect target — potentially a
  foreign origin — defeating the same-origin pin already applied to pagination
  `next` links. Binary attachment downloads still allow redirects (they may
  legitimately point at a blob/CDN URL).
- Release-path GitHub Actions in `publish.yml` are pinned to commit SHAs
  rather than mutable tags, with Dependabot keeping the pins fresh.

### Changed

- The dev extra caps `aiohttp<3.13`: `aioresponses` (through 0.7.9) cannot
  construct aiohttp ≥3.13's `ClientResponse`, which broke the mocked-HTTP
  tests on a fresh install. The **runtime** dependency stays uncapped.

### Docs

- Corrected stale claims across `README.md`, `docs/architecture.md`, and
  `CONTRIBUTING.md`: status banner (0.1.x → 0.2.x), test count (23 → 50),
  endpoint coverage ("all 27" → 25 of 27 wrapped), polite-spacing floor
  (architecture doc said "≥ 1 s"; it is 250 ms), the shipped module map
  (dropped never-shipped `enums.py`/`_senml.py`; 48 → 21 schemas), the
  per-request DEBUG fields, the backoff sequence, and the release process
  (`uv build` + PyPI Trusted Publishing).

## [0.2.1] — 2026-06-10

Error-contract hardening from the remaining audit findings. No API changes.

### Fixed

- `get_bytes` (binary attachment downloads) no longer leaks a raw
  `TimeoutError` — timeouts are now retried and, once retries are
  exhausted, wrapped in `AranetConnectionError`, matching the JSON path
  and the documented "all errors derive from `AranetError`" contract.
- The polite-spacing floor (`_respect_min_interval`) now runs before
  **every** attempt of a binary download, not just once before the retry
  loop, so retries can no longer hammer the API back-to-back.
- A `200` response whose body is valid JSON but not an object (e.g. a
  top-level array or string) now raises `AranetServerError` instead of
  surfacing later as an `AttributeError` outside the exception hierarchy.
- `AranetRateLimitError.retry_after` is now populated from the final 429
  response's `Retry-After` **header** (the value already honoured for
  backoff) instead of attempting to `float()` the response body, which
  effectively always yielded `None`.

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

[Unreleased]: https://github.com/jasonjhofmann/aranet-cloud/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/jasonjhofmann/aranet-cloud/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/jasonjhofmann/aranet-cloud/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/jasonjhofmann/aranet-cloud/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jasonjhofmann/aranet-cloud/releases/tag/v0.1.0
