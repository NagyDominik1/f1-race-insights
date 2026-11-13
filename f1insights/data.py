"""FastF1 data loading. Framework-agnostic: no Streamlit imports here."""

from pathlib import Path

import fastf1
import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
fastf1.Cache.configure(cache_dir=str(CACHE_DIR))


def get_events(year: int) -> pd.DataFrame:
    """Return the race weekends of a season (testing excluded)."""
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    return pd.DataFrame(schedule).reset_index(drop=True)


def load_laps(year: int, event_name: str, session_type: str) -> pd.DataFrame:
    """Return all laps of a session with an extra LapTimeSeconds column."""
    session = fastf1.get_session(year, event_name, session_type)
    session.load(laps=True, telemetry=False, weather=False, messages=False)
    laps = pd.DataFrame(session.laps).reset_index(drop=True)
    laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()
    return laps
