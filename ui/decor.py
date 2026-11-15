"""Decoration: the original logo, the intro splash and the data behind the animated hero bands.

Everything is drawn with SVG, CSS or canvas from the bundled demo race; there are no image
files and no official Formula 1 marks.
"""

import json

import numpy as np
import streamlit as st

from f1insights import analysis, data, telemetry, theme
from ui import loaders

CARS_ON_TRACK = 5
PATH_HZ = 5
TAGLINE = "Formula 1 data, decoded"


def logo_svg(css_class: str = "ri-logo", colour: str = theme.INK) -> str:
    """The original wordmark: three slanted red speed stripes and RACE INSIGHTS."""
    return (
        f'<svg class="{css_class}" viewBox="0 0 566 96" role="img" aria-label="Race Insights">'
        f'<g class="ri-mark" fill="{theme.RED}">'
        '<polygon points="24,20 33,20 15,76 6,76"/><polygon points="45,20 60,20 42,76 27,76"/>'
        '<polygon points="72,20 104,20 86,76 54,76"/></g>'
        f'<text class="ri-word" x="120" y="69" transform="skewX(-9) translate(11 0)" fill="{colour}" stroke="{colour}" '
        'stroke-width="0" font-family="Inter, Helvetica, Arial, sans-serif" font-size="58" letter-spacing="-1.5">'
        '<tspan font-weight="700">RACE</tspan><tspan dx="13" font-weight="400">INSIGHTS</tspan></text></svg>'
    )


def intro_html() -> str:
    """Markup of the start-lights splash; styled by intro.css and driven by intro.js."""
    lamps = "<i></i>" * 5
    return (
        '<div class="ri-intro" id="ri-intro" role="dialog" aria-label="Intro">'
        f'<div class="ri-lights" aria-hidden="true">{lamps}</div>'
        '<div class="ri-stripe" aria-hidden="true"></div>'
        f'<div class="ri-brand"><span data-logo="intro"></span><p class="ri-tag">{TAGLINE}</p></div>'
        '<p class="ri-press"><span class="ri-key">Press any key</span><span class="ri-tap">Tap to start</span></p>'
        '<button class="ri-skip" type="button">Skip intro</button></div>'
    )


def _script_json(value: dict) -> str:
    """JSON for use inside a script element: "<" is escaped so no markup appears in the script text."""
    return json.dumps(value).replace("<", chr(92) + "u003c")


def logo_script() -> str:
    """JavaScript that puts the logo into every [data-logo] placeholder.

    st.html removes inline SVG from its markup, so the SVG is inserted by script instead.
    """
    logos = {"intro": logo_svg("ri-logo ri-draw", "#FFFFFF"), "ink": logo_svg(), "white": logo_svg(colour="#FFFFFF")}
    return (
        f"(() => {{ const LOGOS = {_script_json(logos)}; const put = () => document.querySelectorAll('[data-logo]:empty')"
        ".forEach(el => { el.innerHTML = LOGOS[el.dataset.logo] || LOGOS.ink; });"
        " put(); [100, 400, 1200].forEach(ms => setTimeout(put, ms)); })();"
    )


def _unit(values: np.ndarray) -> list[float]:
    """Values scaled to 0..1, rounded for a compact payload."""
    low, high = np.nanmin(values), np.nanmax(values)
    return np.round((values - low) / max(high - low, 1e-9), 3).tolist()


@st.cache_data(show_spinner=False)
def demo_scene() -> dict | None:
    """Real numbers from the demo race for the animated backgrounds.

    Position lines by lap, five fastest laps on the track outline, two drivers'
    clean lap times, every driver's gap to the fastest lap and the team colours.
    """
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

    clean = loaders.analysed_laps(race_key, True)
    clean = clean.loc[clean["is_clean"]]
    pace = [_unit(clean.loc[clean["acronym"] == name, "LapTimeSeconds"].to_numpy()) for name in order[:2]]
    best = laps.groupby("acronym")["LapTimeSeconds"].min().reindex(order).dropna()
    return {
        "laps": int(by_lap["lap_number"].max()), "lines": lines, "cars": cars,
        "track": {
            "aspect": round(fit["height"] / fit["width"], 4),
            "x": (track_x / fit["width"]).round(4).tolist(),
            "y": (track_y / fit["width"]).round(4).tolist(),
        },
        "pace": pace, "gaps": _unit((best - best.min()).to_numpy()),
        "colours": colours.drop_duplicates().tolist(),
    }
