"""Streamlit entry point for F1 Race Insights."""

import pandas as pd
import plotly.express as px
import streamlit as st

from f1insights import data

SEASONS = list(range(2022, 2027))
SESSIONS = ["Race", "Qualifying"]
DEFAULT_SEASON = 2024
DEFAULT_EVENT = "Hungarian Grand Prix"
DEFAULT_DRIVERS = ["NOR", "PIA"]

st.set_page_config(page_title="F1 Race Insights", page_icon="🏎️", layout="wide")


@st.cache_data(show_spinner=False)
def get_events(year: int) -> pd.DataFrame:
    return data.get_events(year)


@st.cache_data(show_spinner=False)
def load_laps(year: int, event_name: str, session_type: str) -> pd.DataFrame:
    return data.load_laps(year, event_name, session_type)


st.title("F1 Race Insights")

with st.sidebar:
    year = st.selectbox("Season", SEASONS, index=SEASONS.index(DEFAULT_SEASON))

    try:
        with st.spinner("Loading calendar..."):
            event_names = get_events(year)["EventName"].tolist()
    except Exception as exc:
        st.error(f"Could not load the {year} calendar: {exc}")
        st.stop()

    event_index = event_names.index(DEFAULT_EVENT) if DEFAULT_EVENT in event_names else 0
    event_name = st.selectbox("Event", event_names, index=event_index)
    session_type = st.selectbox("Session", SESSIONS)

try:
    with st.spinner(f"Loading {year} {event_name} – {session_type}..."):
        laps = load_laps(year, event_name, session_type)
except Exception as exc:
    st.error(
        f"Could not load {year} {event_name} – {session_type}. "
        f"The session may not be available yet, or the F1 account credentials "
        f"(F1_USERNAME / F1_PASSWORD) are missing.\n\nDetails: {exc}"
    )
    st.stop()

drivers = laps["Driver"].unique().tolist()
default_drivers = (
    DEFAULT_DRIVERS if set(DEFAULT_DRIVERS).issubset(drivers) else drivers[:2]
)
with st.sidebar:
    selected = st.multiselect("Drivers", drivers, default=default_drivers)

if not selected:
    st.info("Select at least one driver in the sidebar.")
    st.stop()

chart_laps = laps.loc[
    laps["Driver"].isin(selected) & laps["LapTimeSeconds"].notna(),
    ["Driver", "LapNumber", "LapTimeSeconds"],
]

fig = px.line(
    chart_laps,
    x="LapNumber",
    y="LapTimeSeconds",
    color="Driver",
    markers=True,
    labels={"LapNumber": "Lap", "LapTimeSeconds": "Lap time (s)"},
    title=f"{year} {event_name} – {session_type}: lap times",
)
st.plotly_chart(fig, width="stretch")
