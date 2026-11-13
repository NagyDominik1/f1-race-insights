"""Build the offline demo data (data/demo/) and the raw test fixtures (tests/fixtures/).

Run from the project root: python scripts/build_demo_data.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from f1insights import data, openf1  # noqa: E402

YEAR = 2024
MEETING_NAME = "Hungarian Grand Prix"
DEMO_SESSIONS = {"Race": "2024_hungary_race", "Qualifying": "2024_hungary_qualifying"}
FIXTURE_SESSION = "Race"
FIXTURE_DRIVERS = ["NOR", "PIA"]
FIXTURE_DIR = ROOT / "tests" / "fixtures"
LAP_PADDING = pd.Timedelta(seconds=1)
SESSION_TABLES = {
    "drivers": data.load_drivers,
    "laps": data.load_laps,
    "stints": data.load_stints,
    "positions": data.load_positions,
    "race_control": data.load_race_control,
    "pit_stops": data.load_pit_stops,
    "results": data.load_results,
}


def records(df) -> list[dict]:
    """DataFrame rows as JSON-serialisable dicts (dates as ISO strings)."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def write_json(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=1), encoding="utf-8")


def write_parquet(df: pd.DataFrame, slug: str, table: str) -> None:
    path = data.DEMO_DIR / f"{slug}_{table}.parquet"
    df.to_parquet(path, index=False)
    print(f"{path.relative_to(ROOT)}: {len(df)} rows, {path.stat().st_size / 1024:.0f} kB")


def fastest_lap_telemetry(session_key: int, laps: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Full-rate location and car data of every driver's fastest lap (padded by 1 s)."""
    location, car = [], []
    for number in laps["driver_number"].unique():
        lap = data.fastest_lap_window(laps, number)
        if lap is None:
            continue
        window = (session_key, number, lap["start"] - LAP_PADDING, lap["end"] + LAP_PADDING)
        location.append(data.load_location(*window, use_demo=False).assign(driver_number=number))
        car.append(data.load_car_data(*window, use_demo=False).assign(driver_number=number))
    as_int = {"driver_number": "Int64"}
    return pd.concat(location).astype(as_int), pd.concat(car).astype(as_int)


def build_demo(sessions: pd.DataFrame) -> None:
    """Write every demo table of each demo session as parquet."""
    data.DEMO_DIR.mkdir(parents=True, exist_ok=True)
    for session in sessions.itertuples():
        key = session.session_key
        for table, loader in SESSION_TABLES.items():
            df = loader(key, use_demo=False)
            if table in ("drivers", "laps", "stints") and df.empty:
                raise SystemExit(f"No {table} returned for {session.session_name}")
            if not df.empty:
                write_parquet(df, session.slug, table)
        laps = data.load_laps(key, use_demo=False)
        lap_location, lap_car_data = fastest_lap_telemetry(key, laps)
        write_parquet(lap_location, session.slug, "lap_location")
        write_parquet(lap_car_data, session.slug, "lap_car_data")
        if session.session_name == "Race":
            progress = lambda done: print(f"  race location {done:.0%}", end="\r")  # noqa: E731
            race_location = data.load_race_location(key, use_demo=False, progress=progress)
            write_parquet(race_location, session.slug, "race_location")


def build_fixtures(session_key: int) -> None:
    """Save small raw API responses of the race for the transform tests."""
    raw_drivers = openf1.get("drivers", session_key=session_key)
    numbers = {d["driver_number"] for d in raw_drivers if d["name_acronym"] in FIXTURE_DRIVERS}
    write_json(FIXTURE_DIR / "drivers.json", raw_drivers)
    write_json(FIXTURE_DIR / "race_control.json", openf1.get("race_control", session_key=session_key))
    write_json(FIXTURE_DIR / "session_result.json", openf1.get("session_result", session_key=session_key))
    for endpoint in ["laps", "stints", "pit", "position"]:
        raw = openf1.get(endpoint, session_key=session_key)
        rows = [row for row in raw if row["driver_number"] in numbers]
        write_json(FIXTURE_DIR / f"{endpoint}_nor_pia.json", rows)

    # NOR's fastest lap at full rate, as returned by the API
    laps = data.load_laps(session_key, use_demo=False)
    number = min(numbers)
    lap = data.fastest_lap_window(laps, number)
    window = {"date>": (lap["start"] - LAP_PADDING).isoformat(), "date<": (lap["end"] + LAP_PADDING).isoformat()}
    for endpoint in ["location", "car_data"]:
        raw = openf1.get(endpoint, session_key=session_key, driver_number=number, **window)
        write_json(FIXTURE_DIR / f"{endpoint}_nor_fastest_lap.json", raw)
    print(f"fixtures: {sum(f.stat().st_size for f in FIXTURE_DIR.iterdir()) / 1024:.0f} kB")


def main() -> None:
    meetings = data.get_meetings(YEAR)
    meeting = meetings.loc[meetings["meeting_name"] == MEETING_NAME]
    sessions = data.get_sessions(int(meeting["meeting_key"].iloc[0]))
    sessions = sessions.loc[sessions["session_name"].isin(DEMO_SESSIONS)]
    sessions = sessions.assign(slug=sessions["session_name"].map(DEMO_SESSIONS))

    build_demo(sessions)
    write_json(
        data.DEMO_DIR / "index.json",
        {"meetings": records(meeting), "sessions": records(sessions)},
    )
    fixture_session = sessions.loc[sessions["session_name"] == FIXTURE_SESSION]
    build_fixtures(int(fixture_session["session_key"].iloc[0]))

    size = sum(f.stat().st_size for f in data.DEMO_DIR.iterdir())
    print(f"data/demo total: {size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
