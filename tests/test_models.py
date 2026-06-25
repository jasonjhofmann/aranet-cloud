"""Model parsing tests — exercise ``from_dict`` against the synthetic
sample responses (structurally identical to real API output).

These guard the spec→model mapping. If Aranet changes a field name or
shape, these tests catch it before users hit it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from aranet_cloud.models import (
    Alarm,
    Base,
    Links,
    Metric,
    Reading,
    Sensor,
    Skill,
)

# ---------------------------------------------------------------------------
# Sensor
# ---------------------------------------------------------------------------


def test_sensor_parses_full_sensor_list(sensors_payload):
    sensors = [Sensor.from_dict(s) for s in sensors_payload["sensors"]]
    assert len(sensors) == 13

    # find the Bedroom Aranet4 by name
    pb = next(s for s in sensors if s.name == "Bedroom")
    assert pb.id == "4000005"
    assert pb.serial == "A0005"
    assert pb.type == "S4V1"
    assert "358151000000001" in pb.bases
    assert pb.active_metrics == ["1", "2", "3", "4", "61", "62"]
    assert pb.primary_base == "358151000000001"


def test_sensor_skills_active_flag():
    raw = {
        "id": "1",
        "sensorId": "ABCDE",
        "name": "Test",
        "type": "S4V1",
        "skills": [
            {"metric": "1", "active": True},
            {"metric": "3", "active": False},  # CO₂ disabled
        ],
    }
    s = Sensor.from_dict(raw)
    assert s.active_metrics == ["1"]


def test_sensor_ignores_unknown_fields():
    """Forward-compat: Aranet adding a field server-side must not break us."""
    raw = {
        "id": "1",
        "sensorId": "ABCDE",
        "name": "X",
        "type": "S4V1",
        "future_field_aranet_added": {"deeply": {"nested": [1, 2, 3]}},
    }
    s = Sensor.from_dict(raw)
    assert s.id == "1"
    assert s.serial == "ABCDE"


def test_sensor_multi_probe_parses(sensors_payload):
    """The S6V1 WET150 soil probe has multiple probes."""
    sensors = [Sensor.from_dict(s) for s in sensors_payload["sensors"]]
    wet150 = next(s for s in sensors if s.type == "S6V1")
    # The skill list should still parse even if probes is empty/missing.
    # The S6V1 sample doesn't have a 'probes' array at the sensor level —
    # just confirm we didn't crash and got the right metric set.
    assert set(wet150.active_metrics) >= {"1", "8", "10", "11"}


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def test_reading_parses_co2_measurement(measurements_last_payload):
    readings = [Reading.from_dict(r) for r in measurements_last_payload["readings"]]
    # Sample has 4 readings: T, RH, CO₂, P
    assert len(readings) == 4
    co2 = next(r for r in readings if r.metric == "3")
    assert co2.sensor == "4000005"
    assert co2.unit == "3"   # ppm
    assert co2.value == 719
    assert co2.novelty == "new"
    assert co2.time is not None
    assert co2.time.tzinfo is not None


def test_reading_handles_missing_time():
    """History responses can have readings without time on edge cases."""
    r = Reading.from_dict({"sensor": "1", "metric": "1", "unit": "1", "value": 22.0})
    assert r.time is None
    assert r.value == 22.0


def test_reading_null_value_is_none():
    """A null value must surface as None, not a genuine-looking 0.0."""
    r = Reading.from_dict(
        {"sensor": "1", "metric": "3", "unit": "3", "value": None, "time": "2026-05-19T23:40:55Z"}
    )
    assert r.value is None


def test_reading_missing_value_is_none():
    r = Reading.from_dict({"sensor": "1", "metric": "3", "unit": "3"})
    assert r.value is None


def test_reading_unparseable_value_is_none():
    """Garbage values become None instead of raising a bare ValueError."""
    r = Reading.from_dict({"sensor": "1", "metric": "3", "unit": "3", "value": "n/a"})
    assert r.value is None
    r2 = Reading.from_dict({"sensor": "1", "metric": "3", "unit": "3", "value": ["odd"]})
    assert r2.value is None


def test_reading_zero_value_stays_zero():
    """A real 0.0 is preserved — only null/garbage map to None."""
    r = Reading.from_dict({"sensor": "1", "metric": "1", "unit": "1", "value": 0})
    assert r.value == 0.0


# ---------------------------------------------------------------------------
# Alarm
# ---------------------------------------------------------------------------


def test_alarm_null_value_and_worst_are_none():
    """Alarm.value/worst follow the same null→None contract as Reading."""
    a = Alarm.from_dict(
        {
            "id": "1",
            "sensor": "4000005",
            "metric": "3",
            "unit": "3",
            "rule": "7",
            "severity": 2,
            "threshold": ">1000",
            "value": None,
            "worst": None,
            "alarmed": "2026-05-19T23:40:55Z",
        }
    )
    assert a.value is None
    assert a.worst is None
    assert a.active


def test_alarm_numeric_values_parse():
    a = Alarm.from_dict({"id": "1", "sensor": "1", "metric": "3", "value": 1432, "worst": "1620.5"})
    assert a.value == 1432.0
    assert a.worst == 1620.5


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


def test_links_resolves_metric_name(measurements_last_payload):
    links = Links.from_dict(measurements_last_payload["links"])
    assert links.name("metric", "3") == "CO₂"
    assert links.name("unit", "3") == "ppm"
    assert links.name("nonexistent_kind", "1") is None
    assert links.name("metric", "9999") is None


def test_links_empty_input():
    assert Links.from_dict(None).by_kind == {}
    assert Links.from_dict({}).by_kind == {}


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


def test_base_parses(bases_payload):
    bases = [Base.from_dict(b) for b in bases_payload["bases"]]
    assert len(bases) == 1
    b = bases[0]
    assert b.id == "358151000000001"
    assert b.name == "Aranet-000001"
    assert b.firmware == "v3.3.6"
    assert b.product == "TDSBWPA2.012"
    assert b.region == "NA"
    assert b.registered_at == datetime(2023, 4, 16, 23, 46, 7, 575689, tzinfo=UTC)
    # consumer accounts: lastSeen is null, config is empty
    assert b.last_seen is None
    assert b.config == {}


# ---------------------------------------------------------------------------
# Metric
# ---------------------------------------------------------------------------


def test_metric_parses_co2(metrics_payload):
    metrics = [Metric.from_dict(m) for m in metrics_payload["metrics"]]
    co2 = next(m for m in metrics if m.name == "CO₂")
    assert co2.id == "3"
    assert co2.is_gauge
    assert not co2.is_telemetry
    assert {u.name for u in co2.units} == {"/", "ppm"}
    default = co2.default_unit
    assert default is not None


def test_metric_kind_telemetry(metrics_payload):
    metrics = [Metric.from_dict(m) for m in metrics_payload["metrics"]]
    rssi = next(m for m in metrics if m.id == "61")
    assert rssi.kind == "t"
    assert rssi.is_telemetry
    battery = next(m for m in metrics if m.id == "62")
    assert battery.is_telemetry


# ---------------------------------------------------------------------------
# defensive coercion (v0.2.2 robustness hardening — from_dict must never crash
# on malformed server data, matching the documented forward-compat contract)
# ---------------------------------------------------------------------------


def test_reading_non_numeric_probe_does_not_crash():
    """A non-numeric integer field (probe) must not raise outside the
    AranetError hierarchy — it defaults to 0 like _as_float_or_none → None."""
    r = Reading.from_dict(
        {"sensor": "1", "metric": "1", "unit": "1", "value": 1.0, "probe": "not-an-int"}
    )
    assert r.probe == 0


def test_reading_float_shaped_int_field_coerces():
    """A float-shaped string for an int field is coerced via float(), not
    dropped to 0."""
    r = Reading.from_dict({"sensor": "1", "metric": "1", "unit": "1", "probe": "2.0"})
    assert r.probe == 2


def test_reading_non_finite_value_is_none():
    """inf/nan — including the string forms float() happily accepts — must not
    masquerade as a genuine measurement."""
    for bad in ("inf", "-inf", "nan", "Infinity", float("inf"), float("nan")):
        r = Reading.from_dict({"sensor": "1", "metric": "3", "unit": "3", "value": bad})
        assert r.value is None, bad


def test_skill_malformed_probes_do_not_crash():
    """Garbage probe indices coerce to 0 and non-mapping probe entries are
    skipped, instead of raising a bare ValueError/TypeError."""
    s = Skill.from_dict(
        {
            "metric": "1",
            "active": True,
            "probes": [{"probe": "bad"}, "not-a-dict", {"probe": 3}],
        }
    )
    assert s.probes == (0, 3)
