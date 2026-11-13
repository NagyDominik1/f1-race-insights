"""Shared selection (season, Grand Prix, session, drivers) kept in session state and the URL."""

from typing import NamedTuple

import pandas as pd
import streamlit as st

from f1insights import data
from f1insights.openf1 import OpenF1Error
from ui import loaders

SEASONS = [2023, 2024, 2025, 2026]
SESSION_NAMES = ["Race", "Qualifying", "Sprint"]
DEFAULT_YEAR = 2024
DEFAULT_MEETING = "Hungarian Grand Prix"
DEFAULT_DRIVERS = ["NOR", "PIA"]
MAX_DRIVERS = 6


class Selection(NamedTuple):
    year: int
    meetings: pd.DataFrame
    meeting: pd.Series
    sessions: pd.DataFrame  # the offered sessions of the weekend, indexed by session_name
    session_name: str
    session_key: int
    available: list[str]  # acronyms with lap data in the session
    drivers: list[str]
    is_demo: bool


def stop_with_error(message: str) -> None:
    """Show a friendly error and end the script run."""
    st.error(message, icon=":material/error:")
    st.stop()


def _from_query_params() -> dict:
    """Initial selection from the URL; anything invalid falls back to the defaults."""
    query = st.query_params
    year, gp, session = query.get("year", ""), query.get("gp", ""), query.get("session", "")
    drivers = [d for d in query.get("drivers", "").upper().split(",") if d.isalnum()]
    return {
        "year": int(year) if year.isdigit() and int(year) in SEASONS else DEFAULT_YEAR,
        "gp": int(gp) if gp.isdigit() else None,
        "session": session if session in SESSION_NAMES else SESSION_NAMES[0],
        "drivers": drivers[:MAX_DRIVERS],
    }


def _default_meeting(meetings: pd.DataFrame) -> int:
    """The demo weekend if present, else the latest weekend that has started."""
    demo = meetings.loc[meetings["meeting_name"] == DEFAULT_MEETING, "meeting_key"]
    if not demo.empty and meetings["year"].iloc[0] == DEFAULT_YEAR:
        return int(demo.iloc[0])
    started = meetings.loc[meetings["date_start"] < pd.Timestamp.now(tz="UTC"), "meeting_key"]
    return int(started.iloc[-1]) if not started.empty else int(meetings["meeting_key"].iloc[0])


def resolve() -> Selection:
    """Validate the stored selection against the data and mirror it into the URL."""
    if "sel" not in st.session_state:
        st.session_state.sel = _from_query_params()
    sel = st.session_state.sel
    try:
        meetings = loaders.meetings(sel["year"])
        if meetings.empty:
            stop_with_error(f"OpenF1 has no race weekends for {sel['year']} yet.")
        if sel["gp"] not in meetings["meeting_key"].tolist():
            sel["gp"] = _default_meeting(meetings)
        meeting = meetings.loc[meetings["meeting_key"] == sel["gp"]].iloc[0]

        sessions = loaders.sessions(sel["gp"])
        sessions = sessions.drop_duplicates("session_name").set_index("session_name")
        sessions = sessions.loc[[name for name in SESSION_NAMES if name in sessions.index]]
        if sessions.empty:
            stop_with_error(
                f"OpenF1 has no race, qualifying or sprint session for the {meeting['meeting_name']} yet."
            )
        if sel["session"] not in sessions.index:
            sel["session"] = sessions.index[0]
        session_key = int(sessions.loc[sel["session"], "session_key"])

        laps = loaders.laps(session_key)
    except OpenF1Error as exc:
        stop_with_error(
            "OpenF1 did not answer, so this session cannot be loaded right now. Try again in a "
            "minute, or switch to the 2024 Hungarian Grand Prix, which works offline."
            f"\n\nDetails: {exc}"
        )

    available = laps.loc[laps["LapTimeSeconds"].notna(), "acronym"].unique().tolist()
    chosen = [d for d in sel["drivers"] if d in available]
    if not chosen:
        chosen = DEFAULT_DRIVERS if set(DEFAULT_DRIVERS) <= set(available) else available[:2]
    sel["drivers"] = chosen
    st.query_params.from_dict({
        "year": str(sel["year"]), "gp": str(sel["gp"]), "session": sel["session"],
        "drivers": ",".join(chosen),
    })
    return Selection(sel["year"], meetings, meeting, sessions, sel["session"], session_key,
                     available, chosen, data.is_demo_session(session_key))


def selector(selection: Selection) -> None:
    """The one reusable selection widget; a change updates the state and reruns."""
    sel = st.session_state.sel
    year = st.selectbox("Season", SEASONS, index=SEASONS.index(selection.year), key="w_year")
    names = selection.meetings.set_index("meeting_key")["meeting_name"]
    keys = names.index.tolist()
    gp = st.selectbox("Grand Prix", keys, index=keys.index(sel["gp"]), format_func=names.get,
                      key=f"w_gp_{selection.year}")
    offered = selection.sessions.index.tolist()
    session = st.segmented_control("Session", offered, default=selection.session_name,
                                   required=True, key=f"w_session_{sel['gp']}")
    drivers = st.multiselect("Drivers", selection.available, default=selection.drivers,
                             max_selections=MAX_DRIVERS, key=f"w_drivers_{selection.session_key}",
                             help="Head-to-head and Ghost lap compare the first two.")
    if not drivers:
        st.caption("Pick at least one driver. Until then the previous choice stays.")
        drivers = selection.drivers
    new = {
        "year": year, "gp": gp if year == selection.year else None,
        "session": session, "drivers": drivers,
    }
    if new != sel:
        st.session_state.sel = new
        st.rerun()
