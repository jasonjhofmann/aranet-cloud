"""Shared test fixtures.

Loads the synthetic sample responses (``docs/sample_*.json``) and exposes
them as fixtures. The payloads are structurally identical to real Aranet
Cloud API responses captured during Phase 0 spec analysis, but every
account-specific identifier (sensor serials, cloud IDs, base-station ID,
base name, room names) has been replaced with a fabricated equivalent.

Note: pre-v0.2.0 revisions of these files contained the original captured
identifiers; they remain in git history.

Also installs a small aioresponses/aiohttp compatibility shim; see
``_patch_client_response_for_aioresponses`` below.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from aiohttp.client_reqrep import ClientResponse

if TYPE_CHECKING:
    from collections.abc import Mapping

DOCS = Path(__file__).resolve().parent.parent / "docs"


class _NullStreamWriter:
    """Stand-in for the stream writer aiohttp>=3.13 reads on construction.

    A mocked response is never actually written to the wire, so aiohttp only
    reads ``output_size`` off this object (client_reqrep records it when the
    request was "already sent").
    """

    output_size = 0


def _patch_client_response_for_aioresponses() -> None:
    """Let aioresponses build responses on aiohttp>=3.13.

    aiohttp 3.13 added a required keyword-only ``stream_writer`` argument to
    ``ClientResponse.__init__``. aioresponses (through 0.7.9, current) does
    not pass it, so every mocked request dies with::

        TypeError: ClientResponse.__init__() missing 1 required
        keyword-only argument: 'stream_writer'

    Default that kwarg rather than capping the test-time aiohttp: this
    package's runtime dependency is uncapped, so pinning the tests to an old
    aiohttp would mean never exercising the version users actually install.

    The shim is self-limiting in both directions — on aiohttp<3.13 the
    parameter does not exist and we skip patching entirely, and once
    aioresponses passes ``stream_writer`` itself the ``setdefault`` becomes a
    no-op. Remove it once aioresponses supports aiohttp>=3.13 natively.
    """
    if "stream_writer" not in inspect.signature(ClientResponse.__init__).parameters:
        return

    original_init = ClientResponse.__init__

    def _init(self: ClientResponse, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("stream_writer", _NullStreamWriter())
        original_init(self, *args, **kwargs)

    ClientResponse.__init__ = _init  # type: ignore[method-assign]


_patch_client_response_for_aioresponses()


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
