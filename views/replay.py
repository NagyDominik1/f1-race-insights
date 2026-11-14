"""Race replay: every car on the track map, with a live running order."""

import json

import streamlit as st

from f1insights import analysis, data, telemetry, theme
from ui import components, loaders

selection = components.page_header()
race_names = [name for name in components.RACE_SESSIONS if name in selection.sessions.index]
if not race_names:
    components.empty_state("OpenF1 has no race session for this weekend yet, so there is nothing to replay.")
# the replay always shows a race: the selected one, or the weekend's Grand Prix when qualifying is selected
session_name = selection.session_name if selection.session_name in race_names else race_names[0]
key = int(selection.sessions.loc[session_name, "session_key"])
if session_name != selection.session_name:
    st.caption(f"The replay shows the {session_name.lower()} of this weekend. {selection.session_name} has no race to replay.")


@st.cache_data(ttl=loaders.TTL, max_entries=2, show_spinner=False)
def build_payload(session_key: int) -> dict | None:
    """The compact replay payload (cached: building it means pivoting ~240 000 rows)."""
    laps, drivers = loaders.laps(session_key), loaders.drivers(session_key)
    positions = loaders.positions(session_key)
    table = analysis.classification(laps, positions, loaders.results(session_key))
    # outline: the fastest lap of the best-placed driver who has one
    candidates = ((int(number), data.fastest_lap_window(laps, number)) for number in table["driver_number"])
    number_used, reference = next(((n, lap) for n, lap in candidates if lap is not None), (None, None))
    if reference is None:
        return None
    location, _ = loaders.lap_telemetry(session_key, number_used, reference["start"], reference["end"])
    race_location = loaders.race_location(session_key)
    if len(location) < 50 or race_location.empty:
        return None
    outline_lap = telemetry.clip_to_window(location, reference["start"], reference["end"])
    periods = analysis.neutralisations(loaders.race_control(session_key))
    return telemetry.replay_payload(
        race_location, outline_lap, laps, positions, loaders.stints(session_key),
        loaders.pit_stops(session_key), periods, drivers, table, data.REPLAY_HZ,
    )


if not data.has_race_location(key):
    # first visit of this race: 20 drivers' positions are fetched from OpenF1 one by one and
    # stored as parquet, so the cached loader below finds them on disk
    bar = st.progress(0.0, text="Fetching car positions from OpenF1. The first load of a race takes up to a minute.")
    with components.loading("Fetching car positions"):
        data.load_race_location(key, progress=lambda done: bar.progress(done, text=f"Fetching car positions from OpenF1: {done:.0%}"))
    bar.empty()
with components.loading("Preparing the replay"):
    payload = build_payload(key)

if payload is None:
    components.empty_state("OpenF1 has no car positions for this race, so it cannot be replayed.")

payload["selected"] = selection.drivers
payload["tyres"] = theme.COMPOUND_COLOURS
components.embed("replay.html", payload, height=760)
size_mb = len(json.dumps(payload, separators=(",", ":"))) / 1e6
st.caption(
    f"Positions are sampled at {data.REPLAY_HZ:g} Hz and interpolated in your browser ({size_mb:.1f} MB for the whole race). "
    "The running order, tyres and pit stops come from the timing data, not from the map. Space bar plays and pauses."
)
components.footer()
