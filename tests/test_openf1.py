"""Tests of the HTTP client's cache and retry logic with a fake session."""

import os
import time

import pytest

from f1insights import openf1


class FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self.ok = status_code < 400
        self._payload = payload
        self.text = str(payload)
        self.headers = {}

    def json(self):
        return self._payload


@pytest.fixture
def fake_api(monkeypatch):
    """Replace the HTTP call with a queue of canned responses; returns the call log."""
    responses, calls = [], []

    def fake_get(url, timeout):
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(openf1._session, "get", fake_get)
    return responses, calls


def test_result_is_cached_on_disk(fake_api):
    responses, calls = fake_api
    responses.append(FakeResponse(200, [{"lap_number": 1}]))
    first = openf1.get("laps", session_key=1)
    second = openf1.get("laps", session_key=1)
    assert first == second == [{"lap_number": 1}]
    assert len(calls) == 1


def test_expired_entry_is_refetched_and_stale_entry_survives_outage(fake_api):
    responses, calls = fake_api
    responses.append(FakeResponse(200, [{"v": 1}]))
    openf1.get("meetings", ttl=60, year=2026)
    path = openf1._cache_path("meetings", {"year": 2026})
    old = time.time() - 120
    os.utime(path, (old, old))

    responses.extend([FakeResponse(503, "down")] * openf1.MAX_TRIES)
    assert openf1.get("meetings", ttl=60, year=2026) == [{"v": 1}]
    assert len(calls) == 1 + openf1.MAX_TRIES

    responses.append(FakeResponse(200, [{"v": 2}]))
    assert openf1.get("meetings", ttl=60, year=2026) == [{"v": 2}]


def test_retries_on_429_then_succeeds(fake_api):
    responses, calls = fake_api
    responses.extend([FakeResponse(429, "slow down"), FakeResponse(200, [{"v": 1}])])
    assert openf1.get("laps", session_key=2) == [{"v": 1}]
    assert len(calls) == 2


def test_client_error_raises_without_retry(fake_api):
    responses, calls = fake_api
    responses.append(FakeResponse(401, "live session"))
    with pytest.raises(openf1.OpenF1Error, match="401"):
        openf1.get("laps", session_key=3)
    assert len(calls) == 1


def test_no_results_is_empty_and_not_cached(fake_api):
    responses, calls = fake_api
    responses.extend([FakeResponse(404, {"detail": "No results found."})] * 2)
    assert openf1.get("laps", session_key=4) == []
    assert openf1.get("laps", session_key=4) == []
    assert len(calls) == 2


def test_range_filters_are_sent_as_operators(fake_api):
    responses, calls = fake_api
    responses.append(FakeResponse(200, [{"x": 1}]))
    openf1.get("location", cache=False, session_key=5, **{"date>": "2024-07-21T14:12:07+00:00", "date<": "b"})
    assert calls[0].endswith("location?session_key=5&date>=2024-07-21T14%3A12%3A07%2B00%3A00&date<=b")
    assert not openf1.CACHE_DIR.exists()
