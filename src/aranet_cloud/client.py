"""High-level :class:`AranetCloudClient` — the public surface of the library.

This is what users import. Each method wraps one Aranet REST endpoint and
returns typed model objects from :mod:`aranet_cloud.models`. Pagination is
exposed as async iterators that hide the ``next`` token mechanics entirely.

Example::

    import asyncio
    from aranet_cloud import AranetCloudClient

    async def main() -> None:
        async with AranetCloudClient(api_key="...") as client:
            sensors = await client.get_sensors()
            for s in sensors:
                print(s.name, s.serial)

            readings, _links = await client.get_measurements_last(sensor=[s.id for s in sensors])
            for r in readings:
                print(r.sensor, r.metric, r.value)

    asyncio.run(main())
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ._http import _Transport
from .const import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    USER_AGENT,
    Endpoint,
)
from .models import (
    Alarm,
    AlarmRule,
    Asset,
    Base,
    Links,
    Metric,
    Reading,
    Sensor,
    SensorType,
    Tag,
    Unit,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable, Mapping

    import aiohttp


def _csv(values: str | Iterable[str | int] | None) -> str | None:
    """Coerce a single value or iterable into the comma-separated form Aranet expects."""
    if values is None:
        return None
    if isinstance(values, str):
        return values
    return ",".join(str(v) for v in values)


def _fmt_dt(value: str | datetime | None) -> str | None:
    """ISO 8601 with second precision; passes through strings unchanged.

    The Aranet API interprets ``from``/``to`` as UTC. A timezone-aware
    datetime is converted to UTC before formatting, so a caller passing e.g. a
    ``US/Pacific`` time does not have its wall-clock digits silently
    reinterpreted as UTC (a multi-hour shift). Naive datetimes are assumed to
    already be UTC and pass through unchanged.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(UTC)
        return value.strftime("%Y-%m-%dT%H:%M:%S")
    return value


def _links_param(links: bool | None) -> str | None:
    """Map the optional ``links`` flag to the API's string query param.

    ``None`` → omit the param (server default applies); ``True``/``False`` →
    the literal ``"true"``/``"false"`` the API expects.
    """
    if links is None:
        return None
    return "true" if links else "false"


class AranetCloudClient:
    """Async client for the Aranet Cloud REST API.

    Two construction patterns:

    * **Owned session** (script / one-shot use)::

          async with AranetCloudClient(api_key="...") as client:
              ...

    * **Injected session** (HA integration, multi-component apps)::

          session = aiohttp_client.async_get_clientsession(hass)
          client = AranetCloudClient(api_key="...", session=session)
          # caller manages session lifecycle

    Parameters:
        api_key: Aranet Cloud API key. Required.
        base_url: Override the default ``https://aranet.cloud`` (for mocking).
        session: Existing ``aiohttp.ClientSession`` to reuse. If omitted, the
            client lazily creates and owns one.
        timeout: Per-request total timeout in seconds.
        max_retries: How many extra attempts on 5xx / 429 / network errors.
        user_agent: HTTP User-Agent header value.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        session: aiohttp.ClientSession | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        user_agent: str = USER_AGENT,
    ) -> None:
        self._transport = _Transport(
            api_key,
            base_url=base_url,
            session=session,
            timeout=timeout,
            max_retries=max_retries,
            user_agent=user_agent,
        )

    async def close(self) -> None:
        """Close the underlying HTTP session (no-op if a session was injected)."""
        await self._transport.close()

    async def __aenter__(self) -> AranetCloudClient:
        await self._transport.__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._transport.__aexit__(*exc)

    # ------------------------------------------------------------------
    # sensors
    # ------------------------------------------------------------------

    async def get_sensors(self, *, base: str | Iterable[str] | None = None) -> list[Sensor]:
        """List all sensors on the account.

        Args:
            base: Filter to one or more base-station IDs.

        Returns:
            List of :class:`Sensor`. Empty list if the account has none.
        """
        data = await self._transport.get_json(Endpoint.SENSORS, params={"base": _csv(base)})
        return [Sensor.from_dict(s) for s in data.get("sensors", []) or []]

    async def get_sensor(self, sensor_id: str | int) -> Sensor:
        """Fetch a single sensor by numeric cloud ID."""
        path = Endpoint.SENSOR.format(sensor=sensor_id)
        data = await self._transport.get_json(path)
        return Sensor.from_dict(data.get("sensor") or data)

    async def get_sensor_types(self) -> list[SensorType]:
        """List every sensor type the cloud knows about (53 in mid-2026)."""
        data = await self._transport.get_json(Endpoint.SENSOR_TYPES)
        return [SensorType.from_dict(t) for t in data.get("sensorTypes", []) or []]

    async def get_sensor_type(self, type_code: str) -> SensorType:
        """Get details on a sensor type by code (e.g. ``"S4V1"``)."""
        path = Endpoint.SENSOR_TYPE.format(sensortype=type_code)
        data = await self._transport.get_json(path)
        return SensorType.from_dict(data.get("sensorType") or data)

    # ------------------------------------------------------------------
    # measurements (gauge metrics: T, RH, CO₂, P, soil...)
    # ------------------------------------------------------------------

    async def get_measurements_last(
        self,
        *,
        sensor: str | Iterable[str] | None = None,
        asset: str | Iterable[str] | None = None,
        point: str | Iterable[str] | None = None,
        metric: str | Iterable[str] | None = None,
        unit: str | Iterable[str] | None = None,
        links: bool | None = None,
    ) -> tuple[list[Reading], Links]:
        """Last measurement per (sensor × metric).

        Returns:
            ``(readings, links)`` — list of readings plus the resolved-name
            helper. Use ``links.name("metric", reading.metric)`` to display
            "CO₂" without a second round-trip.
        """
        params = {
            "sensor": _csv(sensor),
            "asset": _csv(asset),
            "point": _csv(point),
            "metric": _csv(metric),
            "unit": _csv(unit),
            "links": _links_param(links),
        }
        data = await self._transport.get_json(Endpoint.MEASUREMENTS_LAST, params=params)
        return (
            [Reading.from_dict(r) for r in data.get("readings", []) or []],
            Links.from_dict(data.get("links")),
        )

    async def iter_measurements_history(
        self,
        *,
        sensor: str | Iterable[str] | None = None,
        asset: str | Iterable[str] | None = None,
        point: str | Iterable[str] | None = None,
        metric: str | Iterable[str] | None = None,
        unit: str | Iterable[str] | None = None,
        from_: str | datetime | None = None,
        to: str | datetime | None = None,
        seconds: int | None = None,
        minutes: int | None = None,
        hours: int | None = None,
        days: int | None = None,
        limit: int | None = None,
        links: bool | None = None,
    ) -> AsyncIterator[Reading]:
        """Stream every reading in a historical window.

        Follows the ``next`` token transparently. Yields :class:`Reading`
        objects one by one. Time bounds may be ``from_``+``to`` OR one of
        ``seconds``/``minutes``/``hours``/``days`` (not both).

        **Mind the windows:** without ``sensor``, default = last 24 h, max
        = 7 d. With ``sensor``, default = 7 d, max = 6 months. See the
        architecture doc for the full matrix.
        """
        params: dict[str, Any] = {
            "sensor": _csv(sensor),
            "asset": _csv(asset),
            "point": _csv(point),
            "metric": _csv(metric),
            "unit": _csv(unit),
            "from": _fmt_dt(from_),
            "to": _fmt_dt(to),
            "seconds": seconds,
            "minutes": minutes,
            "hours": hours,
            "days": days,
            "limit": limit,
            "links": _links_param(links),
        }
        async for reading in self._paginated_readings(Endpoint.MEASUREMENTS_HISTORY, params):
            yield reading

    # ------------------------------------------------------------------
    # telemetry (RSSI, battery, base status — disjoint from measurements)
    # ------------------------------------------------------------------

    async def get_telemetry_last(
        self,
        *,
        sensor: str | Iterable[str] | None = None,
        metric: str | Iterable[str] | None = None,
        links: bool | None = None,
    ) -> tuple[list[Reading], Links]:
        """Last telemetry reading per (sensor × metric).

        Disjoint metric set from :meth:`get_measurements_last`. For a full
        picture of a sensor's current state, poll both endpoints.
        """
        params = {
            "sensor": _csv(sensor),
            "metric": _csv(metric),
            "links": _links_param(links),
        }
        data = await self._transport.get_json(Endpoint.TELEMETRY_LAST, params=params)
        return (
            [Reading.from_dict(r) for r in data.get("readings", []) or []],
            Links.from_dict(data.get("links")),
        )

    async def iter_telemetry_history(
        self,
        *,
        sensor: str | Iterable[str] | None = None,
        metric: str | Iterable[str] | None = None,
        unit: str | Iterable[str] | None = None,
        from_: str | datetime | None = None,
        to: str | datetime | None = None,
        seconds: int | None = None,
        minutes: int | None = None,
        hours: int | None = None,
        days: int | None = None,
        limit: int | None = None,
        links: bool | None = None,
    ) -> AsyncIterator[Reading]:
        """Stream historical telemetry. Same paging contract as
        :meth:`iter_measurements_history`."""
        params: dict[str, Any] = {
            "sensor": _csv(sensor),
            "metric": _csv(metric),
            "unit": _csv(unit),
            "from": _fmt_dt(from_),
            "to": _fmt_dt(to),
            "seconds": seconds,
            "minutes": minutes,
            "hours": hours,
            "days": days,
            "limit": limit,
            "links": _links_param(links),
        }
        async for reading in self._paginated_readings(Endpoint.TELEMETRY_HISTORY, params):
            yield reading

    # ------------------------------------------------------------------
    # bases
    # ------------------------------------------------------------------

    async def get_bases(self) -> list[Base]:
        """List base stations registered to the account."""
        data = await self._transport.get_json(Endpoint.BASES)
        return [Base.from_dict(b) for b in data.get("bases", []) or []]

    async def get_base(self, base_id: str) -> Base:
        """Fetch details on a specific base station."""
        path = Endpoint.BASE.format(base=base_id)
        data = await self._transport.get_json(path)
        return Base.from_dict(data.get("base") or data)

    # ------------------------------------------------------------------
    # alarms
    # ------------------------------------------------------------------

    async def get_alarms_actual(self) -> list[Alarm]:
        """Currently active alarms (drives ``binary_sensor`` state in HA)."""
        data = await self._transport.get_json(Endpoint.ALARMS_ACTUAL)
        return [Alarm.from_dict(a) for a in data.get("alarms", []) or []]

    async def get_alarms_history(
        self,
        *,
        from_: str | datetime | None = None,
        to: str | datetime | None = None,
    ) -> list[Alarm]:
        """Historical alarm fires within ``[from_, to]``."""
        params = {"from": _fmt_dt(from_), "to": _fmt_dt(to)}
        data = await self._transport.get_json(Endpoint.ALARMS_HISTORY, params=params)
        return [Alarm.from_dict(a) for a in data.get("alarms", []) or []]

    async def get_alarm_rules(self) -> list[AlarmRule]:
        """All alarm rules — built-ins + user-created."""
        data = await self._transport.get_json(Endpoint.ALARM_RULES)
        return [AlarmRule.from_dict(r) for r in data.get("rules", []) or []]

    async def get_alarm_rule(self, rule_id: str | int) -> AlarmRule:
        """Fetch one alarm rule by ID."""
        path = Endpoint.ALARM_RULE.format(rule=rule_id)
        data = await self._transport.get_json(path)
        return AlarmRule.from_dict(data.get("rule") or data)

    # ------------------------------------------------------------------
    # organisation (assets, tags)
    # ------------------------------------------------------------------

    async def get_assets(self) -> list[Asset]:
        """List virtual containers (assets)."""
        data = await self._transport.get_json(Endpoint.ASSETS)
        return [Asset.from_dict(a) for a in data.get("assets", []) or []]

    async def get_asset(self, asset_id: str | int) -> Asset:
        """Fetch a single asset."""
        path = Endpoint.ASSET.format(asset=asset_id)
        data = await self._transport.get_json(path)
        return Asset.from_dict(data.get("asset") or data)

    async def get_tags(self) -> list[Tag]:
        """List all tags."""
        data = await self._transport.get_json(Endpoint.TAGS)
        return [Tag.from_dict(t) for t in data.get("tags", []) or []]

    async def get_tag(self, tag_id: str) -> Tag:
        """Fetch a single tag."""
        path = Endpoint.TAG.format(tag=tag_id)
        data = await self._transport.get_json(path)
        return Tag.from_dict(data.get("tag") or data)

    # ------------------------------------------------------------------
    # catalog (metric / unit lookup tables)
    # ------------------------------------------------------------------

    async def get_metrics(self) -> list[Metric]:
        """List every metric the cloud defines, with available units."""
        data = await self._transport.get_json(Endpoint.METRICS)
        return [Metric.from_dict(m) for m in data.get("metrics", []) or []]

    async def get_metric(self, metric_id: str | int) -> Metric:
        """Fetch a single metric definition."""
        path = Endpoint.METRIC.format(metric=metric_id)
        data = await self._transport.get_json(path)
        return Metric.from_dict(data.get("metric") or data)

    async def get_unit(self, unit_id: str | int) -> Unit:
        """Fetch a single unit definition (incl. recommended ``precision``)."""
        path = Endpoint.UNIT.format(unit=unit_id)
        data = await self._transport.get_json(path)
        return Unit.from_dict(data.get("unit") or data)

    # ------------------------------------------------------------------
    # attachments (binary)
    # ------------------------------------------------------------------

    async def download_sensor_attachment(
        self,
        sensor_id: str | int,
        attachment_id: str,
        *,
        thumbnail: bool = False,
    ) -> bytes:
        """Download a sensor's attached file (e.g. label photo).

        Args:
            sensor_id: Numeric cloud ID.
            attachment_id: The ``{attid}`` path segment of the attachment.
                The API exposes attachments only via ``Sensor.files[*].href``
                (a full URL), so parse the id out of that href rather than
                expecting a standalone field.
            thumbnail: If ``True``, fetch the smaller thumbnail variant.
        """
        tmpl = Endpoint.SENSOR_ATTACHMENT_THUMB if thumbnail else Endpoint.SENSOR_ATTACHMENT_FILE
        return await self._transport.get_bytes(tmpl.format(sensor=sensor_id, attid=attachment_id))

    async def download_asset_attachment(
        self,
        asset_id: str | int,
        attachment_id: str,
        *,
        thumbnail: bool = False,
    ) -> bytes:
        """Download an asset's attached file."""
        tmpl = Endpoint.ASSET_ATTACHMENT_THUMB if thumbnail else Endpoint.ASSET_ATTACHMENT_FILE
        return await self._transport.get_bytes(tmpl.format(asset=asset_id, attid=attachment_id))

    # ------------------------------------------------------------------
    # pagination engine
    # ------------------------------------------------------------------

    async def _paginated_readings(
        self,
        endpoint: str,
        params: Mapping[str, Any],
    ) -> AsyncIterator[Reading]:
        """Generator that follows ``next`` until the API stops returning one.

        The API documents that the last page may be empty (an optimisation
        artifact), so emptiness alone does not stop iteration: we keep going as
        long as a ``next`` URL is supplied and stop the first time it is absent.
        """
        url: str = endpoint
        current_params: Mapping[str, Any] | None = params
        while True:
            data = await self._transport.get_json(url, params=current_params)
            readings = data.get("readings") or []
            for raw in readings:
                yield Reading.from_dict(raw)
            next_url = data.get("next")
            if not next_url:
                return
            url = next_url
            # The next URL already contains all the relevant query string,
            # so we don't pass params again.
            current_params = None
