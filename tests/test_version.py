"""The package's __version__ matches the version it is built and published as."""

from __future__ import annotations

import tomllib
from pathlib import Path

import aranet_cloud


def test_version_matches_pyproject() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text())["project"]
    assert aranet_cloud.__version__ == project["version"]
