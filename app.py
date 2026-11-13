"""Streamlit entry point for F1 Race Insights."""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from f1insights import data
from f1insights.openf1 import OpenF1Error

SEASONS = list(range(2023, 2027))
SESSION_NAMES = ["Race", "Qualifying", "Sprint"]
DEFAULT_SEASON = 2024
DEFAULT_MEETING = "Hungarian Grand Prix"
DEFAULT_DRIVERS = ["NOR", "PIA"]
CACHE_TTL = "6h"

st.set_page_config(page_title="F1 Race Insights", page_icon="🏎️", layout="wide")


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_meetings(year: int) -> pd.DataFrame:
    return data.get_meetings(year)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_sessions(meeting_key: int) -> pd.DataFrame:
    return data.get_sessions(meeting_key)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_drivers(session_key: int) -> pd.DataFrame:
    return data.load_drivers(session_key)


@st.cache_data(ttl=CACHE_TTL, max_entries=20, show_spinner=False)
def load_laps(session_key: int) -> pd.DataFrame:
    return data.load_laps(session_key)


def driver_styles(drivers: pd.DataFrame, selected: list[str]) -> pd.DataFrame:
    """Line colour and dash per selected driver; a repeated team colour is dashed."""
    styles = drivers.set_index("acronym")[["team_colour"]].reindex(selected)
    styles["team_colour"] = styles["team_colour"].fillna(data.FALLBACK_COLOUR)
    styles["dash"] = np.where(styles["team_colour"].duplicated(), "dash", "solid")
    return styles


def stop_with_error(message: str) -> None:
    st.error(message)
    st.stop()


st.title("F1 Race Insights")

with st.sidebar:
    year = st.selectbox("Season", SEASONS, index=SEASONS.index(DEFAULT_SEASON))

    try:
        with st.spinner("Loading calendar..."):
            meetings = get_meetings(year)
    except OpenF1Error as exc:
        stop_with_error(f"Could not load the {year} calendar from OpenF1.\n\nDetails: {exc}")
    if meetings.empty:
        stop_with_error(f"OpenF1 has no race weekends for {year} yet.")

    meeting_names = meetings["meeting_name"].tolist()
    meeting_index = meeting_names.index(DEFAULT_MEETING) if DEFAULT_MEETING in meeting_names else 0
    meeting_name = st.selectbox("Grand Prix", meeting_names, index=meeting_index)
    meeting_key = int(meetings.loc[meetings["meeting_name"] == meeting_name, "meeting_key"].iloc[0])

    try:
        sessions = get_sessions(meeting_key)
    except OpenF1Error as exc:
        stop_with_error(f"Could not load the sessions of the {meeting_name}.\n\nDetails: {exc}")
    session_keys = sessions.set_index("session_name")["session_key"]
    session_names = [name for name in SESSION_NAMES if name in session_keys.index]
    if not session_names:
        stop_with_error(f"OpenF1 has no race, qualifying or sprint session for the {meeting_name} yet.")

    session_name = st.selectbox("Session", session_names)
    session_key = int(session_keys[session_name])
    if data.is_demo_session(session_key):
        st.caption("📦 Served from offline demo data bundled with the app.")

label = f"{year} {meeting_name} – {session_name}"
try:
    with st.spinner(f"Loading {label}..."):
        drivers = load_drivers(session_key)
        laps = load_laps(session_key)
except OpenF1Error as exc:
    stop_with_error(f"Could not load {label} from OpenF1. Please try again later.\n\nDetails: {exc}")

timed_laps = laps.loc[laps["LapTimeSeconds"].notna()]
if timed_laps.empty:
    stop_with_error(f"No lap times available for {label}. The session may not have taken place yet.")

acronyms = timed_laps["acronym"].unique().tolist()
default_drivers = DEFAULT_DRIVERS if set(DEFAULT_DRIVERS).issubset(acronyms) else acronyms[:2]
with st.sidebar:
    selected = st.multiselect("Drivers", acronyms, default=default_drivers)
    st.caption("Data: [OpenF1](https://openf1.org) – unofficial, not affiliated with Formula 1.")

if not selected:
    st.info("Select at least one driver in the sidebar.")
    st.stop()

styles = driver_styles(drivers, selected)
fig = px.line(
    timed_laps.loc[timed_laps["acronym"].isin(selected)],
    x="lap_number",
    y="LapTimeSeconds",
    color="acronym",
    line_dash="acronym",
    color_discrete_map=styles["team_colour"].to_dict(),
    line_dash_map=styles["dash"].to_dict(),
    category_orders={"acronym": selected},
    markers=True,
    labels={"lap_number": "Lap", "LapTimeSeconds": "Lap time (s)", "acronym": "Driver"},
    title=f"{label}: lap times",
)
st.plotly_chart(fig, width="stretch")
