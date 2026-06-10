"""aranet-cloud — async Python client for the Aranet Cloud REST API.

See ``docs/architecture.md`` in the repository for the full API reference
and library architecture.

Quick start::

    import asyncio
    from aranet_cloud import AranetCloudClient

    async def main() -> None:
        async with AranetCloudClient(api_key="...") as client:
            sensors = await client.get_sensors()
            readings, _links = await client.get_measurements_last()
            for r in readings:
                print(r.sensor, r.metric, r.value)

    asyncio.run(main())
"""

from __future__ import annotations

from .client import AranetCloudClient
from .exceptions import (
    AranetAuthError,
    AranetConnectionError,
    AranetError,
    AranetNotFoundError,
    AranetRateLimitError,
    AranetServerError,
    AranetValidationError,
)
from .models import (
    Alarm,
    AlarmRule,
    Asset,
    AssetSensor,
    Base,
    ErrorDetail,
    FileRef,
    Link,
    Links,
    MeasurementPoint,
    MeasurementPointSkill,
    Metric,
    Pairing,
    Probe,
    Reading,
    Sensor,
    SensorType,
    Skill,
    Tag,
    TagType,
    Unit,
)

__version__ = "0.2.0"

__all__ = [
    "Alarm",
    "AlarmRule",
    "AranetAuthError",
    "AranetCloudClient",
    "AranetConnectionError",
    "AranetError",
    "AranetNotFoundError",
    "AranetRateLimitError",
    "AranetServerError",
    "AranetValidationError",
    "Asset",
    "AssetSensor",
    "Base",
    "ErrorDetail",
    "FileRef",
    "Link",
    "Links",
    "MeasurementPoint",
    "MeasurementPointSkill",
    "Metric",
    "Pairing",
    "Probe",
    "Reading",
    "Sensor",
    "SensorType",
    "Skill",
    "Tag",
    "TagType",
    "Unit",
    "__version__",
]
