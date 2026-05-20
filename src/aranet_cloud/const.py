"""Endpoint paths, header names, and other constants.

Path templates use ``{name}`` placeholders that callers substitute via
``str.format`` or ``.format_map``. The base URL is configurable on the
client; tests and air-gapped deployments can point at a mock server.
"""

from __future__ import annotations

from typing import Final

DEFAULT_BASE_URL: Final = "https://aranet.cloud"
"""Production Aranet Cloud base URL. Override via ``AranetCloudClient(base_url=...)``."""

API_KEY_HEADER: Final = "ApiKey"
"""The literal HTTP header name expected by the Aranet API.

Not ``Authorization``. The OpenAPI security scheme declares ``ApiKey`` as
the header name and value is the raw key (no ``Bearer`` prefix).
"""

USER_AGENT: Final = "aranet-cloud-python"
"""Default User-Agent. Callers can override per-client."""


class Endpoint:
    """Path templates for every Aranet API endpoint.

    Use as ``Endpoint.SENSOR.format(sensor=4205836)`` etc. Centralised here so
    paths can be updated in one place if Aranet ever versions the API.
    """

    # Sensors
    SENSORS: Final = "/api/v1/sensors"
    SENSOR: Final = "/api/v1/sensors/sensor/{sensor}"
    SENSOR_TYPES: Final = "/api/v1/sensors/types"
    SENSOR_TYPE: Final = "/api/v1/sensors/types/type/{sensortype}"
    SENSOR_ATTACHMENT: Final = "/api/v1/sensors/sensor/{sensor}/attachment/{attid}"
    SENSOR_ATTACHMENT_FILE: Final = "/api/v1/sensors/sensor/{sensor}/attachment/{attid}/file"
    SENSOR_ATTACHMENT_THUMB: Final = "/api/v1/sensors/sensor/{sensor}/attachment/{attid}/thumbnail"

    # Measurements (gauge readings)
    MEASUREMENTS_LAST: Final = "/api/v1/measurements/last"
    MEASUREMENTS_HISTORY: Final = "/api/v1/measurements/history"

    # Telemetry (sensor-about-sensor: RSSI, battery)
    TELEMETRY_LAST: Final = "/api/v1/telemetry/last"
    TELEMETRY_HISTORY: Final = "/api/v1/telemetry/history"

    # Bases (gateway hardware)
    BASES: Final = "/api/v1/bases"
    BASE: Final = "/api/v1/bases/base/{base}"

    # Alarms
    ALARMS_ACTUAL: Final = "/api/v1/alarms/actual"
    ALARMS_HISTORY: Final = "/api/v1/alarms/history"
    ALARM_RULES: Final = "/api/v1/alarms/rules"
    ALARM_RULE: Final = "/api/v1/alarms/rules/rule/{rule}"

    # Assets (virtual containers)
    ASSETS: Final = "/api/v1/assets"
    ASSET: Final = "/api/v1/assets/asset/{asset}"
    ASSET_ATTACHMENT: Final = "/api/v1/assets/asset/{asset}/attachment/{attid}"
    ASSET_ATTACHMENT_FILE: Final = "/api/v1/assets/asset/{asset}/attachment/{attid}/file"
    ASSET_ATTACHMENT_THUMB: Final = "/api/v1/assets/asset/{asset}/attachment/{attid}/thumbnail"

    # Tags
    TAGS: Final = "/api/v1/tags"
    TAG: Final = "/api/v1/tags/tag/{tag}"

    # Catalog
    METRICS: Final = "/api/v1/metrics"
    METRIC: Final = "/api/v1/metrics/{metric}"
    UNIT: Final = "/api/v1/units/unit/{unit}"


# Retry / backoff defaults — tuned for Cloudflare-fronted Aranet endpoints.
DEFAULT_TIMEOUT: Final = 30.0
DEFAULT_MAX_RETRIES: Final = 3
DEFAULT_BACKOFF_BASE: Final = 1.0
"""Initial backoff in seconds; doubles each retry."""
DEFAULT_BACKOFF_CAP: Final = 30.0
"""Maximum single backoff sleep, regardless of attempt count."""

# Polite-spacing — Aranet documents no rate limit but we don't hammer the API.
MIN_REQUEST_INTERVAL: Final = 0.25
"""Floor between successive requests on the same client. Cheap insurance."""
