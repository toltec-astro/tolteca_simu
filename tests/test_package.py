from __future__ import annotations

import importlib.metadata

import tolteca_simu as m


def test_version() -> None:
    assert importlib.metadata.version("tolteca_simu") == m.__version__
