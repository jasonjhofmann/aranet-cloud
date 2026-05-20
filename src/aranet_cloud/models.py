"""Dataclasses for every API response shape we care about.

These mirror the OpenAPI schemas (see ``docs/openapi.json`` and
``docs/architecture.md``) but use Python-idiomatic naming. The API field
names are documented in each dataclass docstring so future maintainers can
map back to the spec.

Design notes:

* Each model has a ``from_dict`` classmethod that ignores unknown fields —
  this is the contract that lets Aranet add new server-side fields without
  breaking the library.
* String IDs are kept as ``str`` even when they look numeric — the API
  emits them quoted, so we preserve that.
* Datetimes are parsed to ``datetime.datetime`` (timezone-aware, UTC).
* Empty/missing nested arrays default to empty lists, not ``None`` —
  callers can iterate without checking.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp to a timezone-aware datetime.

    Returns ``None`` for ``None`` or empty string. Accepts the ``Z`` suffix
    that Aranet uses (e.g. ``2026-05-19T23:40:55Z``). Python 3.11+
    ``datetime.fromisoformat`` handles ``Z`` natively.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _as_str(value: Any) -> str:
    """Coerce to ``str``, treating ``None`` as empty string."""
    return "" if value is None else str(value)


def _as_float(value: Any) -> float:
    """Coerce to ``float``, treating ``None`` as ``0.0``."""
    if value is None:
        return 0.0
    return float(value)


def _as_int(value: Any) -> int:
    """Coerce to ``int``, treating ``None`` as ``0``."""
    if value is None:
        return 0
    return int(value)


def _as_bool(value: Any) -> bool:
    """Coerce to ``bool``, treating ``None`` as ``False``."""
    return bool(value)


# ---------------------------------------------------------------------------
# links — side-channel of human-readable names for IDs in list responses
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Link:
    """One entry in a ``links.<rel>`` array of a list response.

    API fields: ``rel`` (the ID being named), ``name`` (display string),
    ``href`` (canonical URL for that entity).
    """

    rel: str
    name: str
    href: str

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Link:
        return cls(rel=_as_str(d.get("rel")), name=_as_str(d.get("name")), href=_as_str(d.get("href")))


@dataclass(slots=True)
class Links:
    """Whole ``links`` object — nested ``{rel_kind: [Link, ...]}``.

    Helper methods let callers resolve an ID to its display name without
    hitting the catalog. If ``rel_kind`` isn't present (some endpoints omit
    parts of the links block), lookups return ``None``.

    Example::

        readings, links = ...
        links.name("metric", "3")   # → "CO₂"
    """

    by_kind: dict[str, dict[str, Link]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> Links:
        out = cls()
        if not d:
            return out
        for kind, items in d.items():
            if not isinstance(items, list):
                continue
            bucket: dict[str, Link] = {}
            for raw in items:
                if not isinstance(raw, Mapping):
                    continue
                link = Link.from_dict(raw)
                bucket[link.rel] = link
            out.by_kind[kind] = bucket
        return out

    def link(self, kind: str, rel: str) -> Link | None:
        return self.by_kind.get(kind, {}).get(rel)

    def name(self, kind: str, rel: str) -> str | None:
        link = self.link(kind, rel)
        return link.name if link else None


# ---------------------------------------------------------------------------
# sensor primitives
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Skill:
    """A sensor's declared capability for a given metric.

    API fields: ``metric`` (metric ID), ``active`` (bool — is this skill
    currently reporting), ``probes`` (which probes provide it, for multi-
    probe sensors like the WET150).
    """

    metric: str
    active: bool
    probes: tuple[int, ...] = ()

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Skill:
        return cls(
            metric=_as_str(d.get("metric")),
            active=_as_bool(d.get("active")),
            probes=tuple(int(p["probe"]) for p in d.get("probes", []) or [] if "probe" in p),
        )


@dataclass(slots=True, frozen=True)
class Pairing:
    """Records a sensor↔base pairing event.

    API fields: ``base`` (base ID), ``paired`` (timestamp), ``removed``
    (timestamp or null — None means the pairing is still active).
    """

    base: str
    paired_at: datetime | None
    removed_at: datetime | None

    @property
    def active(self) -> bool:
        """True if the sensor is currently paired (no removal recorded)."""
        return self.removed_at is None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Pairing:
        return cls(
            base=_as_str(d.get("base")),
            paired_at=_parse_dt(d.get("paired")),
            removed_at=_parse_dt(d.get("removed")),
        )


@dataclass(slots=True, frozen=True)
class Probe:
    """One probe on a multi-probe sensor (e.g. each tip of the WET150).

    API fields: ``probe`` (probe index, integer), ``name``, ``label``,
    ``color``.
    """

    probe: int
    name: str
    label: str
    color: str

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Probe:
        return cls(
            probe=_as_int(d.get("probe")),
            name=_as_str(d.get("name")),
            label=_as_str(d.get("label")),
            color=_as_str(d.get("color")),
        )


@dataclass(slots=True, frozen=True)
class FileRef:
    """File attached to a sensor or asset (e.g. label photo).

    API fields: ``name`` (filename), ``href`` (download URL).
    """

    name: str
    href: str

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> FileRef:
        return cls(name=_as_str(d.get("name")), href=_as_str(d.get("href")))


# ---------------------------------------------------------------------------
# sensor
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Sensor:
    """A physical (or virtual) Aranet sensor.

    Two identifiers:

    * ``id``: numeric cloud primary key (e.g. ``"4205836"``). Stable in
      practice but conceptually a cloud-side surrogate.
    * ``serial``: the 5-char hex device identifier printed on the sensor
      (e.g. ``"02D0C"``). Corresponds to API field ``sensorId``. This is
      what HA integrations should use in ``unique_id`` — it survives any
      cloud-side rekeying.

    API field mapping: ``id`` → ``id``, ``sensorId`` → ``serial``, ``name``
    → ``name``, ``type`` → ``type``, ``skills`` → ``skills``, ``bases`` →
    ``bases``, ``pairing`` → ``pairings``, ``probes`` → ``probes``,
    ``tags`` → ``tags``, ``files`` → ``files``.
    """

    id: str
    serial: str
    name: str
    type: str
    skills: list[Skill] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    pairings: list[Pairing] = field(default_factory=list)
    probes: list[Probe] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    files: list[FileRef] = field(default_factory=list)

    @property
    def primary_base(self) -> str | None:
        """The most-recently-paired-and-still-active base ID, or ``None``."""
        active = [p for p in self.pairings if p.active and p.paired_at]
        if not active:
            return None
        active.sort(key=lambda p: p.paired_at or datetime.min.replace(tzinfo=UTC), reverse=True)
        return active[0].base

    @property
    def active_metrics(self) -> list[str]:
        """Metric IDs currently being reported by this sensor."""
        return [s.metric for s in self.skills if s.active]

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Sensor:
        return cls(
            id=_as_str(d.get("id")),
            serial=_as_str(d.get("sensorId")),
            name=_as_str(d.get("name")),
            type=_as_str(d.get("type")),
            skills=[Skill.from_dict(s) for s in d.get("skills", []) or []],
            bases=[_as_str(b) for b in d.get("bases", []) or []],
            pairings=[Pairing.from_dict(p) for p in d.get("pairing", []) or []],
            probes=[Probe.from_dict(p) for p in d.get("probes", []) or []],
            tags=[_as_str(t) for t in d.get("tags", []) or []],
            files=[FileRef.from_dict(f) for f in d.get("files", []) or []],
        )


@dataclass(slots=True, frozen=True)
class SensorType:
    """A type in the Aranet sensor-type catalogue.

    API fields: ``id`` (type code like ``"S4V1"``), ``name`` (display),
    ``isVirtual`` (cloud-computed pseudo-sensor), ``icon`` (mdi-style name),
    ``conversionType`` (nested ``{id}`` — unit-conversion hint).
    """

    id: str
    name: str
    is_virtual: bool
    icon: str
    conversion_type: str

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> SensorType:
        ct = d.get("conversionType") or {}
        return cls(
            id=_as_str(d.get("id")),
            name=_as_str(d.get("name")),
            is_virtual=_as_bool(d.get("isVirtual")),
            icon=_as_str(d.get("icon")),
            conversion_type=_as_str(ct.get("id") if isinstance(ct, Mapping) else None),
        )


# ---------------------------------------------------------------------------
# readings (measurements + telemetry)
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Reading:
    """A single measurement or telemetry datapoint.

    API fields: ``sensor`` (sensor ID), ``metric`` (metric ID), ``unit``
    (unit ID), ``value`` (numeric), ``time`` (ISO 8601 timestamp),
    ``novelty`` (``"new"`` or absent on historical), ``probe`` (probe index
    if multi-probe), ``asset`` / ``point`` (link refs).
    """

    sensor: str
    metric: str
    unit: str
    value: float
    time: datetime | None
    novelty: str = ""
    probe: int = 0
    asset: str = ""
    point: str = ""

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Reading:
        asset = d.get("asset") or {}
        point = d.get("point") or {}
        return cls(
            sensor=_as_str(d.get("sensor")),
            metric=_as_str(d.get("metric")),
            unit=_as_str(d.get("unit")),
            value=_as_float(d.get("value")),
            time=_parse_dt(d.get("time")),
            novelty=_as_str(d.get("novelty")),
            probe=_as_int(d.get("probe")),
            asset=_as_str(asset.get("id") if isinstance(asset, Mapping) else asset),
            point=_as_str(point.get("id") if isinstance(point, Mapping) else point),
        )


# ---------------------------------------------------------------------------
# base stations
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Base:
    """An Aranet base station (gateway hardware).

    API fields: ``id`` (numeric), ``name`` (display, e.g. ``Aranet-75ae36``),
    ``firmware`` (version string), ``product`` (product code),
    ``board`` (board revision), ``region`` (regulatory region),
    ``regdate`` (registration timestamp), ``lastSeen`` (timestamp or null),
    ``pausedate``, ``upgrade``, ``self`` (canonical URL), ``sensors``
    (URL to list sensors), ``tags``, ``config`` (rich nested config dict;
    populated only for enterprise tier — ``{}`` on consumer).
    """

    id: str
    name: str
    firmware: str
    product: str
    board: str
    region: str
    registered_at: datetime | None
    last_seen: datetime | None
    self_url: str = ""
    sensors_url: str = ""
    tags: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Base:
        return cls(
            id=_as_str(d.get("id")),
            name=_as_str(d.get("name")),
            firmware=_as_str(d.get("firmware")),
            product=_as_str(d.get("product")),
            board=_as_str(d.get("board")),
            region=_as_str(d.get("region")),
            registered_at=_parse_dt(d.get("regdate")),
            last_seen=_parse_dt(d.get("lastSeen")),
            self_url=_as_str(d.get("self")),
            sensors_url=_as_str(d.get("sensors")),
            tags=[_as_str(t) for t in d.get("tags", []) or []],
            config=dict(d.get("config", {}) or {}),
        )


# ---------------------------------------------------------------------------
# alarms
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Alarm:
    """An active or historical alarm event.

    API fields: ``id``, ``sensor``, ``metric``, ``unit``, ``rule``,
    ``severity`` (int), ``threshold``, ``value``, ``worst`` (numeric peak
    during the alarm), ``alarmed`` (when fired), ``resolved`` (when cleared,
    or null if still active), ``note``.
    """

    id: str
    sensor: str
    metric: str
    unit: str
    rule: str
    severity: int
    threshold: str
    value: float
    worst: float
    alarmed_at: datetime | None
    resolved_at: datetime | None
    note: str = ""

    @property
    def active(self) -> bool:
        """True if the alarm has not been resolved."""
        return self.resolved_at is None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Alarm:
        return cls(
            id=_as_str(d.get("id")),
            sensor=_as_str(d.get("sensor")),
            metric=_as_str(d.get("metric")),
            unit=_as_str(d.get("unit")),
            rule=_as_str(d.get("rule")),
            severity=_as_int(d.get("severity")),
            threshold=_as_str(d.get("threshold")),
            value=_as_float(d.get("value")),
            worst=_as_float(d.get("worst")),
            alarmed_at=_parse_dt(d.get("alarmed")),
            resolved_at=_parse_dt(d.get("resolved")),
            note=_as_str(d.get("note")),
        )


@dataclass(slots=True, frozen=True)
class AlarmRule:
    """A configured alarm rule (user-created or built-in).

    API fields: ``id``, ``name``, ``metric`` (the metric this rule watches),
    ``notes`` (free text — built-in rules describe their behaviour here),
    ``created`` (timestamp).

    The two built-in rules every account has are *Low battery* (metric 62)
    and *Base station offline* (metric 81). User-created rules add to this
    list.
    """

    id: str
    name: str
    metric: str
    notes: str
    created_at: datetime | None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> AlarmRule:
        return cls(
            id=_as_str(d.get("id")),
            name=_as_str(d.get("name")),
            metric=_as_str(d.get("metric")),
            notes=_as_str(d.get("notes")),
            created_at=_parse_dt(d.get("created")),
        )


# ---------------------------------------------------------------------------
# catalog: metric + unit
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Unit:
    """A unit of measure (e.g. ``°C``, ``ppm``, ``%``).

    API fields: ``id``, ``name``, ``precision`` (recommended decimal
    places for displaying values in this unit), ``default``, ``selected``.

    ``precision`` is the most important field for HA integrations — pass
    it through as the ``suggested_display_precision`` on sensor entities.
    """

    id: str
    name: str
    precision: int
    default: bool = False
    selected: bool = False

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Unit:
        return cls(
            id=_as_str(d.get("id")),
            name=_as_str(d.get("name")),
            precision=_as_int(d.get("precision")),
            default=_as_bool(d.get("default")),
            selected=_as_bool(d.get("selected")),
        )


@dataclass(slots=True, frozen=True)
class Metric:
    """A metric definition (e.g. CO₂, Temperature, RSSI).

    API fields: ``id``, ``name``, ``kind`` (``"g"`` gauge / ``"t"``
    telemetry), ``units`` (list of available Units), ``icon``,
    ``sensors`` (count of sensors reporting this metric — cloud-computed).

    The integration uses ``kind`` to decide whether a metric belongs in
    ``measurements/last`` (gauge) or ``telemetry/last`` (telemetry).
    """

    id: str
    name: str
    kind: str
    units: list[Unit] = field(default_factory=list)
    icon: str = ""
    sensors_count: int = 0

    @property
    def is_gauge(self) -> bool:
        return self.kind == "g"

    @property
    def is_telemetry(self) -> bool:
        return self.kind == "t"

    @property
    def default_unit(self) -> Unit | None:
        for u in self.units:
            if u.default:
                return u
        return self.units[0] if self.units else None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Metric:
        return cls(
            id=_as_str(d.get("id")),
            name=_as_str(d.get("name")),
            kind=_as_str(d.get("kind")),
            units=[Unit.from_dict(u) for u in d.get("units", []) or []],
            icon=_as_str(d.get("icon")),
            sensors_count=_as_int(d.get("sensors")),
        )


# ---------------------------------------------------------------------------
# tags
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class TagType:
    """A tag's category (color/icon hints for UI grouping)."""

    id: str
    name: str
    color: str = ""
    icon: str = ""

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> TagType:
        return cls(
            id=_as_str(d.get("id")),
            name=_as_str(d.get("name")),
            color=_as_str(d.get("color")),
            icon=_as_str(d.get("icon")),
        )


@dataclass(slots=True, frozen=True)
class Tag:
    """A tag for organizing sensors/assets."""

    id: str
    name: str
    notes: str = ""
    type: TagType | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Tag:
        raw_type = d.get("type")
        return cls(
            id=_as_str(d.get("id")),
            name=_as_str(d.get("name")),
            notes=_as_str(d.get("notes")),
            type=TagType.from_dict(raw_type) if isinstance(raw_type, Mapping) else None,
        )


# ---------------------------------------------------------------------------
# assets
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class MeasurementPointSkill:
    """A skill within an asset measurement-point (analogous to Sensor.Skill)."""

    metric: str
    active: bool

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> MeasurementPointSkill:
        return cls(metric=_as_str(d.get("metric")), active=_as_bool(d.get("active")))


@dataclass(slots=True, frozen=True)
class AssetSensor:
    """A sensor placed at an asset measurement-point.

    API fields: ``id``, ``sensor`` (sensor ID), ``probe`` (probe index),
    ``placed`` (when installed), ``removed`` (when removed, or null).
    """

    id: str
    sensor: str
    probe: int
    placed_at: datetime | None
    removed_at: datetime | None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> AssetSensor:
        return cls(
            id=_as_str(d.get("id")),
            sensor=_as_str(d.get("sensor")),
            probe=_as_int(d.get("probe")),
            placed_at=_parse_dt(d.get("placed")),
            removed_at=_parse_dt(d.get("removed")),
        )


@dataclass(slots=True, frozen=True)
class MeasurementPoint:
    """A point within an asset where measurements are collected."""

    id: str
    name: str
    skills: list[MeasurementPointSkill] = field(default_factory=list)
    associations: list[AssetSensor] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> MeasurementPoint:
        return cls(
            id=_as_str(d.get("id")),
            name=_as_str(d.get("name")),
            skills=[MeasurementPointSkill.from_dict(s) for s in d.get("skills", []) or []],
            associations=[AssetSensor.from_dict(a) for a in d.get("associations", []) or []],
        )


@dataclass(slots=True)
class Asset:
    """A virtual container (e.g. "Greenhouse Zone A") with measurement points.

    API fields: ``id``, ``name``, ``location``, ``notes``, ``points`` (list
    of MeasurementPoint), ``tags`` (list of tag IDs), ``files``.
    """

    id: str
    name: str
    location: str = ""
    notes: str = ""
    points: list[MeasurementPoint] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    files: list[FileRef] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Asset:
        return cls(
            id=_as_str(d.get("id")),
            name=_as_str(d.get("name")),
            location=_as_str(d.get("location")),
            notes=_as_str(d.get("notes")),
            points=[MeasurementPoint.from_dict(p) for p in d.get("points", []) or []],
            tags=[_as_str(t) for t in d.get("tags", []) or []],
            files=[FileRef.from_dict(f) for f in d.get("files", []) or []],
        )


# ---------------------------------------------------------------------------
# error envelope
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class ErrorDetail:
    """One entry in a 400 response's ``error[]`` array.

    API fields: ``message``, ``id`` (server-side correlation token —
    log this on errors so users can ask Aranet support to look it up).
    """

    message: str
    id: str
    details: list[Mapping[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ErrorDetail:
        return cls(
            message=_as_str(d.get("message")),
            id=_as_str(d.get("id")),
            details=list(d.get("details", []) or []),
        )


__all__ = [
    "Alarm",
    "AlarmRule",
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
]
