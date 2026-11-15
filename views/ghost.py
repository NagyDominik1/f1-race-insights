"""Ghost lap: two drivers' fastest laps on the same track, compared by distance."""

import pandas as pd
import streamlit as st

from f1insights import analysis, data, telemetry, theme
from ui import charts, components, loaders

selection = components.page_header("races")
if len(selection.drivers) < 2:
    components.empty_state("Pick two drivers under Change race to set their fastest laps against each other.",
                           title="A ghost lap needs two drivers")
first, second = selection.drivers[:2]

# the lap comes from qualifying when the weekend has one: that is where drivers push hardest
offered = selection.sessions.index.tolist()
default = "Qualifying" if "Qualifying" in offered else selection.session_name
session_name = st.segmented_control("Fastest laps from", offered, default=default, required=True, key="ghost_session")
key = int(selection.sessions.loc[session_name, "session_key"])


@st.cache_data(ttl=loaders.TTL, max_entries=12, show_spinner=False)
def fastest_ghost_lap(session_key: int, acronym: str) -> tuple[pd.DataFrame, pd.Series, pd.Series] | None:
    """A driver's fastest lap resampled by distance, with the lap and driver rows; None if unavailable."""
    drivers, laps = loaders.drivers(session_key), loaders.laps(session_key)
    driver = drivers.loc[drivers["acronym"] == acronym]
    if driver.empty:
        return None
    lap = data.fastest_lap_window(laps, driver["driver_number"].iloc[0])
    if lap is None:
        return None
    location, car = loaders.lap_telemetry(session_key, int(driver["driver_number"].iloc[0]), lap["start"], lap["end"])
    inside = location["date"].between(lap["start"], lap["end"]).sum()
    if inside < 100 or car.empty or location["date"].min() > lap["start"] or location["date"].max() < lap["end"]:
        return None
    return telemetry.ghost_lap(location, car, lap["start"], lap["end"]), lap, driver.iloc[0]


with components.loading("Loading both laps"):
    ghosts = [fastest_ghost_lap(key, name) for name in (first, second)]
missing = [name for name, ghost in zip((first, second), ghosts) if ghost is None]
if missing:
    components.empty_state(
        f"OpenF1 has no usable fastest lap with car positions for {' and '.join(missing)} in {session_name.lower()}. "
        "Try another session or driver."
    )

(lap_a, info_a, driver_a), (lap_b, info_b, driver_b) = ghosts
sectors = telemetry.mini_sectors(lap_a, lap_b)
cars = [
    {"a": name, "c": driver["team_colour"], "note": f"lap {info['lap_number']}, {driver['team_name'] or ''}"}
    for name, info, driver in [(first, info_a, driver_a), (second, info_b, driver_b)]
]
payload = telemetry.ghost_payload(lap_a, lap_b, sectors, cars) | {"even": telemetry.EVEN_SECONDS}
components.embed("ghost.html", payload)
st.caption(
    f"The track is cut into {telemetry.MINI_SECTORS} mini-sectors of equal distance and coloured by the driver who was "
    f"faster there. Time inside the lap is rebuilt from distance and measured speed and is good to roughly five "
    f"hundredths, so gaps under {telemetry.EVEN_SECONDS} s count as too close to call. The gap at the finish equals "
    "the official lap-time gap. The cars are drawn side by side so both stay visible; that offset is visual only."
)

styles = theme.driver_styles(loaders.drivers(key), [first, second])
speed, delta = st.columns(2)
with speed, components.tile("speed"):
    components.tile_heading("Speed around the lap", "Where one line is above the other, that driver carried more speed.")
    components.plot(charts.speed_trace(lap_a, lap_b, first, second, styles), "speed")
with delta, components.tile("delta"):
    gap = float(telemetry.lap_delta(lap_a, lap_b)[-1])
    components.tile_heading(
        "Where the time was won",
        f"Running gap, {first} minus {second}. Below zero {first} is ahead; a falling line means {first} is gaining. "
        f"It ends at {gap:+.3f} s ({analysis.format_lap_time(info_a['seconds'])} against "
        f"{analysis.format_lap_time(info_b['seconds'])}).",
    )
    components.plot(charts.delta_trace(lap_a, lap_b, first, second, styles), "ghost-delta")
components.footer()
