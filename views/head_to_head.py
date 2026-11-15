"""Head-to-head: two drivers compared lap by lap (race) or on their best lap (qualifying)."""

import pandas as pd
import streamlit as st

from f1insights import analysis, theme
from ui import charts, components, loaders

selection = components.page_header()
key, race = selection.session_key, components.is_race(selection)

if len(selection.drivers) < 2:
    components.empty_state("Pick two drivers under Change race. Team-mates make the fairest comparison.",
                           title="Head-to-head needs two drivers")
first, second = selection.drivers[:2]

with components.loading("Loading lap times"):
    laps = loaders.analysed_laps(key, race)
    drivers = loaders.drivers(key)
styles = theme.driver_styles(drivers, [first, second])


def ghost_link() -> None:
    if st.button("Watch the ghost lap", type="primary", icon=":material/play_arrow:"):
        st.switch_page("views/ghost.py")
    st.caption(f"{first} and {second} drive their fastest laps against each other on the track map.")


def race_view() -> None:
    deltas = analysis.lap_deltas(laps, first, second)
    if len(deltas) < 3:
        components.empty_state(f"{first} and {second} have fewer than three laps that are clean for both.")
    median, low, high = analysis.bootstrap_median_ci(deltas["delta"].to_numpy())
    faster, slower = (first, second) if median < 0 else (second, first)
    decided = low > 0 or high < 0
    tiles = [
        {"label": "Median gap per lap", "number": abs(median), "decimals": 3, "suffix": " s", "accent": True,
         "note": f"in favour of {faster}"},
        {"label": "95% confidence interval", "text": f"{low:+.3f} to {high:+.3f} s", "small": True, "note": f"{first} minus {second}, seconds"},
        {"label": "Laps compared", "number": len(deltas), "note": "clean for both drivers"},
        {"label": f"Laps where {first} was faster", "number": int((deltas["delta"] < 0).sum()),
         "note": f"{second}: {int((deltas['delta'] >= 0).sum())}"},
    ]
    components.embed("kpi.html", {"tiles": tiles})
    chart, side = st.columns([2, 1])
    with chart, components.tile("delta"):
        components.tile_heading(
            f"{first} against {second}, lap by lap",
            f"Bars below zero are laps where {first} was faster, bars above zero belong to {second}. "
            "The dotted line is the median, the grey band its 95% interval.",
        )
        components.plot(charts.delta_figure(deltas, first, second, styles, median, low, high), "delta")
    with side, components.tile("verdict", "carbon"):
        components.tile_heading("What the interval says")
        if decided:
            st.markdown(
                f"The whole interval is on {faster}'s side of zero, so on comparable laps **{faster} was faster "
                f"than {slower}**, by about {abs(median):.3f} s per lap. Chance alone is an unlikely explanation."
            )
        else:
            st.markdown(
                f"The interval includes zero. {faster} was ahead on the median lap, but these laps **do not "
                f"clearly separate** the two drivers."
            )
        st.caption(
            f"Bootstrap: the {len(deltas)} lap gaps are resampled with replacement "
            f"{analysis.BOOTSTRAP_RESAMPLES} times and the median is taken each time. The interval is the middle "
            "95% of those medians. The seed is fixed, so the numbers are reproducible."
        )
    with side, components.tile("ghost", "sky"):
        ghost_link()


def qualifying_view() -> None:
    table = analysis.best_lap_comparison(laps, first, second)
    if table[[first, second]].loc[0].isna().any():
        components.empty_state(f"{first} or {second} has no timed lap in this session.")
    gap = float(table.loc[0, "gap"])
    faster = first if gap < 0 else second
    tiles = [
        {"label": "Best-lap gap", "number": abs(gap), "decimals": 3, "suffix": " s", "accent": True,
         "note": f"in favour of {faster}"},
        {"label": f"{first} best lap", "number": float(table.loc[0, first]), "format": "laptime", "note": ""},
        {"label": f"{second} best lap", "number": float(table.loc[0, second]), "format": "laptime", "note": ""},
    ]
    components.embed("kpi.html", {"tiles": tiles})
    chart, side = st.columns([2, 1])
    with chart, components.tile("sectors"):
        components.tile_heading("Where the gap comes from",
                                "Sector times of each driver's best lap. The label on a bar names the faster driver.")
        if table[[first, second]].isna().any().any():
            st.caption("OpenF1 is missing a sector time for one of these laps, so only the lap gap is shown.")
        else:
            components.plot(charts.sector_figure(table, first, second, styles), "sectors")
        show = pd.DataFrame({
            "": table["part"], first: table[first].map(analysis.format_lap_time),
            second: table[second].map(analysis.format_lap_time), "Gap (s)": table["gap"].map("{:+.3f}".format),
        })
        components.table(show)
    with side, components.tile("ghost", "sky"):
        ghost_link()


if race:
    race_view()
else:
    qualifying_view()
components.footer()
