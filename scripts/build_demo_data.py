"""Build the offline demo data (data/demo/) and the raw test fixtures (tests/fixtures/).

Run from the project root: python scripts/build_demo_data.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from f1insights import data, openf1  # noqa: E402

YEAR = 2024
MEETING_NAME = "Hungarian Grand Prix"
DEMO_SESSIONS = {"Race": "2024_hungary_race", "Qualifying": "2024_hungary_qualifying"}
FIXTURE_SESSION = "Race"
FIXTURE_DRIVERS = ["NOR", "PIA"]
FIXTURE_DIR = ROOT / "tests" / "fixtures"


def records(df) -> list[dict]:
    """DataFrame rows as JSON-serialisable dicts (dates as ISO strings)."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def write_json(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=1), encoding="utf-8")


def build_demo(sessions) -> None:
    """Write drivers, laps and stints of each demo session as parquet."""
    data.DEMO_DIR.mkdir(parents=True, exist_ok=True)
    loaders = {
        "drivers": data.load_drivers,
        "laps": data.load_laps,
        "stints": data.load_stints,
    }
    for session in sessions.itertuples():
        for table, loader in loaders.items():
            df = loader(session.session_key, use_demo=False)
            if df.empty:
                raise SystemExit(f"No {table} returned for {session.session_name}")
            path = data.DEMO_DIR / f"{session.slug}_{table}.parquet"
            df.to_parquet(path, index=False)
            print(f"{path.relative_to(ROOT)}: {len(df)} rows")


def build_fixtures(session_key: int) -> None:
    """Save raw API responses: all drivers, laps and stints of two drivers."""
    raw_drivers = openf1.get("drivers", session_key=session_key)
    numbers = {d["driver_number"] for d in raw_drivers if d["name_acronym"] in FIXTURE_DRIVERS}
    write_json(FIXTURE_DIR / "drivers.json", raw_drivers)
    for endpoint in ["laps", "stints"]:
        raw = openf1.get(endpoint, session_key=session_key)
        rows = [row for row in raw if row["driver_number"] in numbers]
        write_json(FIXTURE_DIR / f"{endpoint}_nor_pia.json", rows)
        print(f"tests/fixtures/{endpoint}_nor_pia.json: {len(rows)} rows")


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
    print(f"data/demo total: {size / 1024:.0f} kB")


if __name__ == "__main__":
    main()
