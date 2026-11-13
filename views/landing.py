"""Landing page: a split screen with two tiles, Analytics and Races."""

import numpy as np
import streamlit as st

from f1insights import analysis, data, telemetry
from ui import components, loaders, state

CARS_ON_TRACK = 5
PATH_HZ = 5


@st.cache_data(show_spinner=False)
def landing_payload() -> dict | None:
    """Background data from the demo race: positions by lap and fastest laps on the outline."""
    race_key = data.demo_sessions().get("Race")
    if race_key is None:
        return None
    laps, drivers = loaders.laps(race_key), loaders.drivers(race_key)
    order = loaders.results(race_key)["acronym"].tolist()
    by_lap = analysis.position_by_lap(laps, loaders.positions(race_key))
    lines = by_lap.pivot(index="lap_number", columns="acronym", values="position")
    lines = lines.reindex(columns=order).astype("float64")
    lines = [[None if np.isnan(v) else int(v) for v in lines[name]] for name in lines.columns]

    colours = drivers.set_index("acronym")["team_colour"]
    numbers = drivers.set_index("acronym")["driver_number"]
    cars, fit, outline = [], None, None
    for acronym in order[:CARS_ON_TRACK]:
        lap = data.fastest_lap_window(laps, numbers[acronym])
        location, _ = loaders.lap_telemetry(race_key, int(numbers[acronym]), lap["start"], lap["end"])
        path = telemetry.clip_to_window(location, lap["start"], lap["end"])
        if fit is None:
            outline = telemetry.track_outline(path, points=240)
            fit = telemetry.fit_to_box(outline["x"], outline["y"])
        t = np.arange(0, lap["seconds"], 1 / PATH_HZ)
        x, y = telemetry.to_box(np.interp(t, path["t"], path["x"]), np.interp(t, path["t"], path["y"]), fit)
        cars.append({
            "label": acronym, "colour": colours[acronym], "seconds": round(lap["seconds"], 3),
            "x": (x / fit["width"]).round(4).tolist(), "y": (y / fit["width"]).round(4).tolist(),
        })
    track_x, track_y = telemetry.to_box(outline["x"], outline["y"], fit)
    return {
        "laps": int(by_lap["lap_number"].max()), "lines": lines, "cars": cars,
        "track": {
            "aspect": round(fit["height"] / fit["width"], 4),
            "x": (track_x / fit["width"]).round(4).tolist(),
            "y": (track_y / fit["width"]).round(4).tolist(),
        },
    }


def tile_html(canvas_id: str, title: str, text: str, cta: str) -> str:
    return (
        f'<div class="lt-tile"><canvas id="{canvas_id}" aria-hidden="true"></canvas>'
        f'<div class="lt-copy"><h2>{title}</h2><p>{text}</p><span class="lt-cta">{cta}</span></div></div>'
    )


state.resolve()  # keeps the selection in the URL, so a shared link opens the same race
st.html(f"<style>{components._template('landing.css')}</style>")

with st.container(key="landing"):
    st.html(
        '<div class="lt-brand"><b>F1 Race Insights</b>'
        "<span>Formula 1 timing data from 2023 to 2026, analysed and replayed.</span></div>"
    )
    analytics, races = st.columns(2)
    with analytics.container(key="lt-analytics"):
        st.html(tile_html(
            "lt-lines", "Analytics",
            "Pace, tyre strategy and head-to-head statistics, with the method behind every number.",
            "Open analytics",
        ))
        if st.button("Open analytics", key="go_analytics"):
            st.switch_page("views/overview.py")
    with races.container(key="lt-races"):
        st.html(tile_html(
            "lt-track", "Races",
            "Replay a Grand Prix on the track map, or set two fastest laps against each other.",
            "Watch the replay",
        ))
        if st.button("Watch the replay", key="go_races"):
            st.switch_page("views/replay.py")
    st.html(
        f'<div class="lt-foot"><span>Built by Dominik Nagy. <a href="{components.REPO_URL}" '
        f'target="_blank" rel="noopener">Source on GitHub</a></span><span>{components.DISCLAIMER}</span></div>'
    )

payload = landing_payload()
if payload:
    script = components.render_template("landing.js", payload)
    st.html(f"<script>{script}</script>", unsafe_allow_javascript=True)
