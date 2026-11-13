"""Thin HTTP client for the OpenF1 REST API with a JSON disk cache."""

import hashlib
import json
import time
from pathlib import Path

import requests

BASE_URL = "https://api.openf1.org/v1"
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "openf1"
TIMEOUT = 30
MAX_TRIES = 4

_session = requests.Session()
_session.headers["User-Agent"] = "f1-race-insights/0.1"


class OpenF1Error(Exception):
    """The OpenF1 API could not be reached or returned an unusable response."""


def get(endpoint: str, ttl: float | None = None, **params) -> list[dict]:
    """Return the rows of an endpoint, served from the disk cache when possible.

    ttl is the maximum cache age in seconds; None caches forever. If the API
    fails and an expired cache entry exists, the stale entry is returned.
    """
    path = _cache_path(endpoint, params)
    if _is_fresh(path, ttl):
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        rows = _fetch(endpoint, params)
    except OpenF1Error:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        raise
    # empty answers (e.g. a session that has not started) are never cached
    if rows:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows), encoding="utf-8")
    return rows


def _cache_path(endpoint: str, params: dict) -> Path:
    """Cache file for a request: endpoint name + hash of the sorted params."""
    key = json.dumps(sorted((name, str(value)) for name, value in params.items()))
    digest = hashlib.sha1(key.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{endpoint}_{digest}.json"


def _is_fresh(path: Path, ttl: float | None) -> bool:
    """True if the cache file exists and is younger than ttl (None = forever)."""
    if not path.exists():
        return False
    return ttl is None or time.time() - path.stat().st_mtime < ttl


def _fetch(endpoint: str, params: dict) -> list[dict]:
    """Request an endpoint, retrying with exponential backoff on 429 and 5xx."""
    for attempt in range(MAX_TRIES):
        try:
            response = _session.get(
                f"{BASE_URL}/{endpoint}", params=params, timeout=TIMEOUT
            )
        except requests.RequestException as exc:
            raise OpenF1Error(f"OpenF1 is unreachable ({endpoint}): {exc}") from exc
        status = response.status_code
        # OpenF1 answers a query without results with 404 "No results found."
        if status == 404 and "No results" in response.text:
            return []
        if response.ok:
            return _rows(endpoint, response)
        if status != 429 and status < 500:
            break
        if attempt < MAX_TRIES - 1:
            time.sleep(2**attempt)
    raise OpenF1Error(
        f"OpenF1 request failed ({endpoint} {params}): "
        f"HTTP {status} {response.text[:200]}"
    )


def _rows(endpoint: str, response: requests.Response) -> list[dict]:
    """Decode a successful response, which must be a JSON list of rows."""
    try:
        rows = response.json()
    except ValueError as exc:
        raise OpenF1Error(f"OpenF1 returned invalid JSON ({endpoint})") from exc
    if not isinstance(rows, list):
        raise OpenF1Error(f"OpenF1 returned an unexpected payload ({endpoint}): {rows}")
    return rows
