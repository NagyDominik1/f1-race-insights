"""Shared fixtures. Tests never touch the network or the real disk cache."""

import json
from pathlib import Path

import pytest
import requests

from f1insights import data, openf1

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    """Fail on any HTTP request and point the disk cache to a temp folder."""

    def blocked(*args, **kwargs):
        raise AssertionError("Tests must not access the network")

    monkeypatch.setattr(requests.Session, "send", blocked)
    monkeypatch.setattr(openf1, "CACHE_DIR", tmp_path / "openf1")
    monkeypatch.setattr(openf1.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(openf1, "MIN_INTERVAL", 0)


def load_fixture(name: str) -> list[dict]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def raw_drivers() -> list[dict]:
    return load_fixture("drivers.json")


@pytest.fixture
def raw_laps() -> list[dict]:
    return load_fixture("laps_nor_pia.json")


@pytest.fixture
def raw_stints() -> list[dict]:
    return load_fixture("stints_nor_pia.json")


@pytest.fixture
def drivers(raw_drivers):
    return data.drivers_from_raw(raw_drivers)
