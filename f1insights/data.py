"""Loading functions returning pandas DataFrames. No Streamlit imports here.

Every loader is a fetch (openf1.get or a demo parquet file) plus a pure
``*_from_raw`` transform that only does pandas work and is unit tested.
"""

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

from f1insights import openf1

SIX_HOURS = 6 * 3600
DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "demo"
FALLBACK_COLOUR = "#808080"

MEETING_COLUMNS = [
    "meeting_key", "meeting_name", "country_name", "circuit_short_name",
    "year", "date_start", "date_end",
]
SESSION_COLUMNS = [
    "session_key", "meeting_key", "session_name", "session_type",
    "date_start", "date_end",
]
DRIVER_RENAMES = {
    "driver_number": "driver_number",
    "name_acronym": "acronym",
    "full_name": "full_name",
    "team_name": "team_name",
    "team_colour": "team_colour",
}
LAP_RENAMES = {
    "driver_number": "driver_number",
    "lap_number": "lap_number",
    "lap_duration": "LapTimeSeconds",
    "duration_sector_1": "Sector1Seconds",
    "duration_sector_2": "Sector2Seconds",
    "duration_sector_3": "Sector3Seconds",
    "is_pit_out_lap": "is_pit_out_lap",
    "date_start": "date_start",
}
LAP_COLUMNS = [
    "driver_number", "acronym", "team_name", "lap_number", "LapTimeSeconds",
    "Sector1Seconds", "Sector2Seconds", "Sector3Seconds", "is_pit_out_lap",
    "date_start",
]
STINT_COLUMNS = [
    "driver_number", "acronym", "stint_number", "compound", "lap_start",
    "lap_end", "tyre_age_at_start",
]


# --- pure transforms -------------------------------------------------------

def meetings_from_raw(raw: list[dict]) -> pd.DataFrame:
    """Race weekends sorted by date; testing and cancelled events are dropped."""
    meetings = pd.DataFrame(raw, columns=[*MEETING_COLUMNS, "is_cancelled"])
    is_testing = meetings["meeting_name"].str.contains("testing", case=False)
    is_cancelled = meetings["is_cancelled"].astype("boolean").fillna(False)
    meetings = meetings.loc[~is_testing & ~is_cancelled, MEETING_COLUMNS]
    return _with_utc_dates(meetings).sort_values("date_start").reset_index(drop=True)


def sessions_from_raw(raw: list[dict]) -> pd.DataFrame:
    """Sessions of a weekend (practice, qualifying, sprint, race) sorted by date."""
    sessions = pd.DataFrame(raw, columns=SESSION_COLUMNS)
    return _with_utc_dates(sessions).sort_values("date_start").reset_index(drop=True)


def drivers_from_raw(raw: list[dict]) -> pd.DataFrame:
    """One row per driver: driver_number, acronym, full_name, team_name, team_colour.

    OpenF1 sends team_colour as "RRGGBB" in mixed case and sometimes not at all;
    it is normalised to "#RRGGBB" with a grey fallback. A missing acronym is
    replaced by the driver number; full_name and team_name can be null.
    """
    drivers = pd.DataFrame(raw, columns=list(DRIVER_RENAMES)).rename(columns=DRIVER_RENAMES)
    drivers = drivers.astype({"driver_number": "Int64"} | dict.fromkeys(
        ["acronym", "full_name", "team_name", "team_colour"], "string"))
    colour = drivers["team_colour"].str.upper()
    is_hex = colour.str.fullmatch("[0-9A-F]{6}").fillna(False)
    drivers["team_colour"] = ("#" + colour).where(is_hex, FALLBACK_COLOUR)
    drivers["acronym"] = drivers["acronym"].fillna(drivers["driver_number"].astype("string"))
    drivers = drivers.drop_duplicates("driver_number").sort_values("driver_number")
    return drivers.reset_index(drop=True)


def laps_from_raw(raw: list[dict], drivers: pd.DataFrame) -> pd.DataFrame:
    """One row per driver and lap, sorted by driver_number and lap_number.

    Nulls to expect: LapTimeSeconds is missing on laps with incomplete timing
    (pit-lane start on lap 1, the lap of a retirement, the first out lap and
    aborted laps in qualifying). Sector1Seconds is missing on pit-out laps and
    occasionally on a normal lap; date_start can be missing on lap 1.
    team_name is null when the driver is absent from the session's driver list.
    Values are not filtered: outside races a pit-out lap's time includes the
    time spent in the garage and can exceed 1000 s.
    """
    laps = pd.DataFrame(raw, columns=list(LAP_RENAMES)).rename(columns=LAP_RENAMES)
    seconds = ["LapTimeSeconds", "Sector1Seconds", "Sector2Seconds", "Sector3Seconds"]
    laps = laps.astype(
        {"driver_number": "Int64", "lap_number": "Int64", "is_pit_out_lap": "boolean"}
        | dict.fromkeys(seconds, "float64")
    )
    laps = _with_utc_dates(laps, ["date_start"])
    laps = laps.drop_duplicates(["driver_number", "lap_number"])
    laps = _add_driver_info(laps, drivers, ["acronym", "team_name"])
    laps = laps.sort_values(["driver_number", "lap_number"])
    return laps[LAP_COLUMNS].reset_index(drop=True)


def stints_from_raw(raw: list[dict], drivers: pd.DataFrame) -> pd.DataFrame:
    """One row per driver and stint, sorted by driver_number and stint_number.

    compound is upper case; an unreported compound becomes "UNKNOWN".
    lap_start, lap_end and tyre_age_at_start can be null while a stint is
    still being timed or when the tyre data was never published.
    """
    numbers = ["driver_number", "stint_number", "lap_start", "lap_end", "tyre_age_at_start"]
    stints = pd.DataFrame(raw, columns=[*numbers, "compound"])
    stints = stints.astype(dict.fromkeys(numbers, "Int64") | {"compound": "string"})
    stints["compound"] = stints["compound"].str.upper().fillna("UNKNOWN")
    stints = stints.drop_duplicates(["driver_number", "stint_number"])
    stints = _add_driver_info(stints, drivers, ["acronym"])
    stints = stints.sort_values(["driver_number", "stint_number"])
    return stints[STINT_COLUMNS].reset_index(drop=True)


def _with_utc_dates(df: pd.DataFrame, columns: tuple | list = ("date_start", "date_end")) -> pd.DataFrame:
    """Parse ISO date strings (with or without fractional seconds) as UTC."""
    parsed = {col: pd.to_datetime(df[col], format="ISO8601", utc=True) for col in columns}
    return df.assign(**parsed)


def _add_driver_info(df: pd.DataFrame, drivers: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Left-join driver columns; unknown drivers get their number as acronym."""
    merged = df.merge(
        drivers[["driver_number", *columns]], on="driver_number", how="left", validate="m:1"
    )
    merged["acronym"] = merged["acronym"].fillna(merged["driver_number"].astype("string"))
    return merged


# --- demo data -------------------------------------------------------------

@lru_cache
def _demo_index() -> dict:
    """Content of data/demo/index.json (empty if no demo data is bundled)."""
    path = DEMO_DIR / "index.json"
    if not path.exists():
        return {"meetings": [], "sessions": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _demo_path(session_key: int, table: str) -> Path | None:
    """Parquet file of a demo session's table, or None for non-demo sessions."""
    slugs = {s["session_key"]: s["slug"] for s in _demo_index()["sessions"]}
    slug = slugs.get(int(session_key))
    return DEMO_DIR / f"{slug}_{table}.parquet" if slug else None


def is_demo_session(session_key: int) -> bool:
    """True if the session is bundled as offline demo data."""
    return _demo_path(session_key, "laps") is not None


# --- loaders ---------------------------------------------------------------

def get_meetings(year: int) -> pd.DataFrame:
    """Race weekends of a season; falls back to the demo index if OpenF1 is down."""
    ttl = None if year < pd.Timestamp.now(tz="UTC").year else SIX_HOURS
    try:
        raw = openf1.get("meetings", ttl=ttl, year=year)
    except openf1.OpenF1Error:
        raw = [m for m in _demo_index()["meetings"] if m["year"] == year]
        if not raw:
            raise
    return meetings_from_raw(raw)


def get_sessions(meeting_key: int) -> pd.DataFrame:
    """Sessions of a weekend; falls back to the demo index if OpenF1 is down."""
    try:
        raw = openf1.get("sessions", ttl=SIX_HOURS, meeting_key=meeting_key)
    except openf1.OpenF1Error:
        raw = [s for s in _demo_index()["sessions"] if s["meeting_key"] == meeting_key]
        if not raw:
            raise
    return sessions_from_raw(raw)


def load_drivers(session_key: int, use_demo: bool = True) -> pd.DataFrame:
    """Drivers of a session, see drivers_from_raw."""
    if use_demo and (path := _demo_path(session_key, "drivers")):
        return pd.read_parquet(path)
    raw = openf1.get("drivers", ttl=_session_ttl(session_key), session_key=session_key)
    return drivers_from_raw(raw)


def load_laps(session_key: int, use_demo: bool = True) -> pd.DataFrame:
    """Laps of a session, see laps_from_raw."""
    if use_demo and (path := _demo_path(session_key, "laps")):
        return pd.read_parquet(path)
    raw = openf1.get("laps", ttl=_session_ttl(session_key), session_key=session_key)
    return laps_from_raw(raw, load_drivers(session_key, use_demo))


def load_stints(session_key: int, use_demo: bool = True) -> pd.DataFrame:
    """Tyre stints of a session, see stints_from_raw."""
    if use_demo and (path := _demo_path(session_key, "stints")):
        return pd.read_parquet(path)
    raw = openf1.get("stints", ttl=_session_ttl(session_key), session_key=session_key)
    return stints_from_raw(raw, load_drivers(session_key, use_demo))


def _session_ttl(session_key: int) -> float | None:
    """Cache TTL for session data: forever once it ended over six hours ago."""
    raw = openf1.get("sessions", ttl=SIX_HOURS, session_key=session_key)
    ends = sessions_from_raw(raw)["date_end"]
    settled = ends.max() + pd.Timedelta(seconds=SIX_HOURS) < pd.Timestamp.now(tz="UTC")
    return None if settled else SIX_HOURS
