"""Loading functions returning pandas DataFrames. No Streamlit imports here.

Every loader is a fetch (openf1.get or a demo parquet file) plus a pure
``*_from_raw`` transform that only does pandas work and is unit tested.
"""

import json
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import pandas as pd

from f1insights import openf1, telemetry

SIX_HOURS = 6 * 3600
ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "data" / "demo"
DERIVED_DIR = ROOT / "cache" / "derived"
REPLAY_HZ = 2.0
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
POSITION_COLUMNS = ["date", "driver_number", "acronym", "position"]
RACE_CONTROL_COLUMNS = [
    "date", "lap_number", "category", "flag", "scope", "driver_number", "message",
]
PIT_COLUMNS = ["driver_number", "acronym", "lap_number", "pit_duration", "date"]
RESULT_COLUMNS = [
    "driver_number", "acronym", "position", "number_of_laps", "dnf", "dns", "dsq",
]
LOCATION_COLUMNS = ["date", "x", "y"]
CAR_DATA_COLUMNS = ["date", "speed", "throttle", "brake", "n_gear", "rpm", "drs"]
RACE_LOCATION_COLUMNS = ["date", "driver_number", "x", "y"]


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


def positions_from_raw(raw: list[dict], drivers: pd.DataFrame) -> pd.DataFrame:
    """Position changes over time: one row each time a driver's position changes.

    The first row of a driver is the starting grid slot, the last one the
    position at the flag (before any post-race penalty).
    """
    positions = pd.DataFrame(raw, columns=["date", "driver_number", "position"])
    positions = positions.astype({"driver_number": "Int64", "position": "Int64"})
    positions = _with_utc_dates(positions, ["date"]).dropna(subset=["date", "position"])
    positions = _add_driver_info(positions, drivers, ["acronym"])
    positions = positions.sort_values("date", kind="stable")
    return positions[POSITION_COLUMNS].reset_index(drop=True)


def race_control_from_raw(raw: list[dict]) -> pd.DataFrame:
    """Race control messages sorted by time.

    lap_number is the leader's lap and is null outside races; flag, scope and
    driver_number are null for messages that are not about a flag or a driver.
    """
    messages = pd.DataFrame(raw, columns=RACE_CONTROL_COLUMNS)
    messages = messages.astype(
        {"lap_number": "Int64", "driver_number": "Int64"}
        | dict.fromkeys(["category", "flag", "scope", "message"], "string")
    )
    messages = _with_utc_dates(messages, ["date"])
    return messages.sort_values("date", kind="stable").reset_index(drop=True)


def pit_stops_from_raw(raw: list[dict], drivers: pd.DataFrame) -> pd.DataFrame:
    """One row per pit stop; lap_number is the in-lap.

    pit_duration is the time spent in the pit lane in seconds (not the
    stationary time) and can be null when timing was incomplete.
    """
    stops = pd.DataFrame(raw, columns=["driver_number", "lap_number", "pit_duration", "date"])
    stops = stops.astype(
        {"driver_number": "Int64", "lap_number": "Int64", "pit_duration": "float64"}
    )
    stops = _add_driver_info(_with_utc_dates(stops, ["date"]), drivers, ["acronym"])
    stops = stops.sort_values(["driver_number", "lap_number"])
    return stops[PIT_COLUMNS].reset_index(drop=True)


def results_from_raw(raw: list[dict], drivers: pd.DataFrame) -> pd.DataFrame:
    """Official classification sorted by position; unclassified drivers last.

    position is null for drivers who did not finish, start or were disqualified.
    """
    flags = ["dnf", "dns", "dsq"]
    results = pd.DataFrame(raw, columns=["driver_number", "position", "number_of_laps", *flags])
    results = results.astype(
        dict.fromkeys(["driver_number", "position", "number_of_laps"], "Int64")
        | dict.fromkeys(flags, "boolean")
    )
    results[flags] = results[flags].fillna(False)
    results = _add_driver_info(results, drivers, ["acronym"])
    results = results.sort_values(
        ["position", "number_of_laps"], ascending=[True, False], na_position="last"
    )
    return results[RESULT_COLUMNS].reset_index(drop=True)


def location_from_raw(raw: list[dict]) -> pd.DataFrame:
    """Car positions (date, x, y) sorted by time; x and y are in 1/10 metre.

    OpenF1 reports (0, 0) before a car's transponder is live; those rows and
    duplicated timestamps are dropped.
    """
    location = pd.DataFrame(raw, columns=LOCATION_COLUMNS)
    location = _with_utc_dates(location, ["date"]).dropna()
    location = location.loc[(location["x"] != 0) | (location["y"] != 0)]
    location = location.astype({"x": "int32", "y": "int32"})
    return location.drop_duplicates("date").sort_values("date").reset_index(drop=True)


def car_data_from_raw(raw: list[dict]) -> pd.DataFrame:
    """Car telemetry sorted by time: speed (km/h), throttle and brake (0-100),
    n_gear, rpm and the raw drs code. Rows with a missing value are dropped."""
    car = pd.DataFrame(raw, columns=CAR_DATA_COLUMNS)
    car = _with_utc_dates(car, ["date"]).dropna()
    car = car.astype(dict.fromkeys(CAR_DATA_COLUMNS[1:], "int32"))
    return car.drop_duplicates("date").sort_values("date").reset_index(drop=True)


def fastest_lap_window(laps: pd.DataFrame, driver_number: int) -> pd.Series | None:
    """Fastest timed lap of a driver: lap_number, seconds, start and end (UTC).

    Laps without a start time and pit-out laps are ignored; None if nothing is left.
    """
    own = laps.loc[
        (laps["driver_number"] == driver_number)
        & laps["LapTimeSeconds"].notna()
        & laps["date_start"].notna()
        & ~laps["is_pit_out_lap"].fillna(False)
    ]
    if own.empty:
        return None
    lap = own.loc[own["LapTimeSeconds"].idxmin()]
    end = lap["date_start"] + pd.Timedelta(seconds=lap["LapTimeSeconds"])
    return pd.Series({
        "lap_number": int(lap["lap_number"]), "seconds": float(lap["LapTimeSeconds"]),
        "start": lap["date_start"], "end": end,
    })


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


def _demo_table(session_key: int, table: str) -> pd.DataFrame | None:
    """A bundled demo table of a session, or None if it is not bundled."""
    path = _demo_path(session_key, table)
    return pd.read_parquet(path) if path and path.exists() else None


def demo_sessions() -> dict[str, int]:
    """Session keys of the bundled demo weekend by session name (Race, Qualifying)."""
    return {s["session_name"]: s["session_key"] for s in _demo_index()["sessions"]}


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


def _session_ttl(session_key: int) -> float | None:
    """Cache TTL for session data: forever once it ended over six hours ago."""
    raw = openf1.get("sessions", ttl=SIX_HOURS, session_key=session_key)
    ends = sessions_from_raw(raw)["date_end"]
    settled = ends.max() + pd.Timedelta(seconds=SIX_HOURS) < pd.Timestamp.now(tz="UTC")
    return None if settled else SIX_HOURS


def _fetch(endpoint: str, session_key: int, **params) -> list[dict]:
    """Raw rows of a session endpoint, cached according to the session's age."""
    ttl = _session_ttl(session_key)
    return openf1.get(endpoint, ttl=ttl, session_key=session_key, **params)


def load_drivers(session_key: int, use_demo: bool = True) -> pd.DataFrame:
    """Drivers of a session, see drivers_from_raw."""
    if use_demo and (demo := _demo_table(session_key, "drivers")) is not None:
        return demo
    return drivers_from_raw(_fetch("drivers", session_key))


def load_laps(session_key: int, use_demo: bool = True) -> pd.DataFrame:
    """Laps of a session, see laps_from_raw."""
    if use_demo and (demo := _demo_table(session_key, "laps")) is not None:
        return demo
    return laps_from_raw(_fetch("laps", session_key), load_drivers(session_key, use_demo))


def load_stints(session_key: int, use_demo: bool = True) -> pd.DataFrame:
    """Tyre stints of a session, see stints_from_raw."""
    if use_demo and (demo := _demo_table(session_key, "stints")) is not None:
        return demo
    return stints_from_raw(_fetch("stints", session_key), load_drivers(session_key, use_demo))


def load_positions(session_key: int, use_demo: bool = True) -> pd.DataFrame:
    """Position changes of a session, see positions_from_raw."""
    if use_demo and (demo := _demo_table(session_key, "positions")) is not None:
        return demo
    return positions_from_raw(_fetch("position", session_key), load_drivers(session_key, use_demo))


def load_race_control(session_key: int, use_demo: bool = True) -> pd.DataFrame:
    """Race control messages of a session, see race_control_from_raw."""
    if use_demo and (demo := _demo_table(session_key, "race_control")) is not None:
        return demo
    return race_control_from_raw(_fetch("race_control", session_key))


def load_pit_stops(session_key: int, use_demo: bool = True) -> pd.DataFrame:
    """Pit stops of a session, see pit_stops_from_raw."""
    if use_demo and (demo := _demo_table(session_key, "pit_stops")) is not None:
        return demo
    return pit_stops_from_raw(_fetch("pit", session_key), load_drivers(session_key, use_demo))


def load_results(session_key: int, use_demo: bool = True) -> pd.DataFrame:
    """Official classification of a session (can be empty), see results_from_raw."""
    if use_demo and (demo := _demo_table(session_key, "results")) is not None:
        return demo
    return results_from_raw(_fetch("session_result", session_key), load_drivers(session_key, use_demo))


def _load_window(
    endpoint: str, table: str, transform: Callable[[list[dict]], pd.DataFrame],
    session_key: int, driver_number: int, start: pd.Timestamp, end: pd.Timestamp,
    use_demo: bool,
) -> pd.DataFrame:
    """Telemetry of one driver between start and end, from demo data if covered."""
    if use_demo and (demo := _demo_table(session_key, table)) is not None:
        rows = demo.loc[(demo["driver_number"] == driver_number) & demo["date"].between(start, end)]
        if not rows.empty:
            return rows.drop(columns="driver_number").reset_index(drop=True)
    window = {"date>": start.isoformat(), "date<": end.isoformat()}
    return transform(_fetch(endpoint, session_key, driver_number=int(driver_number), **window))


def load_location(
    session_key: int, driver_number: int, start: pd.Timestamp, end: pd.Timestamp,
    use_demo: bool = True,
) -> pd.DataFrame:
    """Full-rate (~3.7 Hz) car positions of one driver in a time window."""
    return _load_window("location", "lap_location", location_from_raw,
                        session_key, driver_number, start, end, use_demo)


def load_car_data(
    session_key: int, driver_number: int, start: pd.Timestamp, end: pd.Timestamp,
    use_demo: bool = True,
) -> pd.DataFrame:
    """Full-rate (~3.7 Hz) car telemetry of one driver in a time window."""
    return _load_window("car_data", "lap_car_data", car_data_from_raw,
                        session_key, driver_number, start, end, use_demo)


def load_race_location(
    session_key: int, use_demo: bool = True,
    progress: Callable[[float], None] | None = None,
) -> pd.DataFrame:
    """Positions of every driver on a shared REPLAY_HZ time grid (date, driver_number, x, y).

    A race is ~35 000 location rows per driver (~4.5 MB of JSON), so each driver
    is fetched separately, resampled at once and the raw rows are discarded.
    The result of a finished session is stored as parquet in cache/derived/.
    progress, if given, is called with the fraction of drivers done.
    """
    if use_demo and (demo := _demo_table(session_key, "race_location")) is not None:
        return demo
    path = DERIVED_DIR / f"race_location_{int(session_key)}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    grid = telemetry.time_grid(load_laps(session_key, use_demo), REPLAY_HZ)
    numbers = load_drivers(session_key, use_demo)["driver_number"].tolist()
    parts = []
    for done, number in enumerate(numbers, start=1):
        if len(grid):
            window = {"date>": grid[0].isoformat(), "date<": grid[-1].isoformat()}
            raw = openf1.get("location", cache=False, session_key=session_key,
                             driver_number=number, **window)
            resampled = telemetry.resample_location(location_from_raw(raw), grid)
            parts.append(resampled.assign(driver_number=number))
        if progress:
            progress(done / len(numbers))
    if not parts:
        return pd.DataFrame(columns=RACE_LOCATION_COLUMNS)
    location = pd.concat(parts, ignore_index=True).astype({"driver_number": "Int64"})
    location = location[RACE_LOCATION_COLUMNS]
    if _session_ttl(session_key) is None and not location.empty:
        path.parent.mkdir(parents=True, exist_ok=True)
        location.to_parquet(path, index=False)
    return location
