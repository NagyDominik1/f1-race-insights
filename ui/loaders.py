"""st.cache_data wrappers around f1insights.data (the only place results are cached in memory)."""

from collections.abc import Callable

import pandas as pd
import streamlit as st

from f1insights import analysis, data

TTL = "6h"


def _cached(loader: Callable, max_entries: int = 12) -> Callable:
    return st.cache_data(ttl=TTL, max_entries=max_entries, show_spinner=False)(loader)


meetings = _cached(data.get_meetings, max_entries=8)
sessions = _cached(data.get_sessions, max_entries=64)
drivers = _cached(data.load_drivers)
laps = _cached(data.load_laps)
stints = _cached(data.load_stints)
positions = _cached(data.load_positions)
race_control = _cached(data.load_race_control)
pit_stops = _cached(data.load_pit_stops)
results = _cached(data.load_results)


@st.cache_data(ttl=TTL, max_entries=2, show_spinner=False)
def race_location(session_key: int, _progress: Callable[[float], None] | None = None) -> pd.DataFrame:
    """2 Hz positions of all drivers; the heaviest table, so only two races stay in memory."""
    return data.load_race_location(session_key, progress=_progress)


@st.cache_data(ttl=TTL, max_entries=24, show_spinner=False)
def lap_telemetry(
    session_key: int, driver_number: int, start: pd.Timestamp, end: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Full-rate location and car data of one lap, padded by one second on both sides."""
    pad = pd.Timedelta(seconds=1)
    location = data.load_location(session_key, driver_number, start - pad, end + pad)
    car = data.load_car_data(session_key, driver_number, start - pad, end + pad)
    return location, car


@st.cache_data(ttl=TTL, max_entries=8, show_spinner=False)
def analysed_laps(session_key: int, race: bool) -> pd.DataFrame:
    """Laps flagged by the clean-lap filter and matched to their tyre stint."""
    periods = analysis.neutralisations(race_control(session_key))
    flagged = analysis.clean_laps(laps(session_key), pit_stops(session_key), periods,
                                  reference="median" if race else "min")
    return analysis.with_stints(flagged, stints(session_key))
