"""Shared test fixtures.

Loads the synthetic sample responses (``docs/sample_*.json``) and exposes
them as fixtures. The payloads are structurally identical to real Aranet
Cloud API responses captured during Phase 0 spec analysis, but every
account-specific identifier (sensor serials, cloud IDs, base-station ID,
base name, room names) has been replaced with a fabricated equivalent.

Note: pre-v0.2.0 revisions of these files contained the original captured
identifiers; they remain in git history.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping

DOCS = Path(__file__).resolve().parent.parent / "docs"


def _load(name: str) -> Mapping[str, Any]:
    return json.loads((DOCS / name).read_text())


@pytest.fixture
def sensors_payload() -> Mapping[str, Any]:
    """Synthetic ``GET /api/v1/sensors`` response (13 sensors)."""
    return _load("sample_sensors.json")


@pytest.fixture
def bases_payload() -> Mapping[str, Any]:
    """Synthetic ``GET /api/v1/bases`` response (1 base)."""
    return _load("sample_bases.json")


@pytest.fixture
def metrics_payload() -> Mapping[str, Any]:
    """Synthetic ``GET /api/v1/metrics`` response (14 metrics)."""
    return _load("sample_metrics.json")


@pytest.fixture
def measurements_last_payload() -> Mapping[str, Any]:
    """Synthetic ``GET /api/v1/measurements/last?sensor=4000005`` response."""
    return _load("sample_measurements_last.json")
