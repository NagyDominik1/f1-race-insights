"""Strategy: tyre stints of every driver and tyre degradation per stint."""

import pandas as pd
import streamlit as st

from f1insights import analysis, theme
from ui import charts, components, loaders

selection = components.page_header()
key, race = selection.session_key, components.is_race(selection)

with components.loading("Loading tyre data"):
    laps = loaders.analysed_laps(key, race)
    drivers = loaders.drivers(key)
    stints = loaders.stints(key)
    pit_stops = loaders.pit_stops(key)
    table = analysis.classification(laps, loaders.positions(key), loaders.results(key))

stints = stints.dropna(subset=["lap_start", "lap_end"])
if stints.empty:
    components.empty_state("OpenF1 has no tyre stints for this session.")


def timeline_payload() -> dict:
    """Stints and pit stops per driver in finishing order, as plain records for the HTML timeline."""
    bars = stints.assign(
        start=stints["lap_start"].astype(int), end=stints["lap_end"].astype(int),
        age=stints["tyre_age_at_start"].fillna(0).astype(int),
        colour=stints["compound"].map(theme.compound_colour),
        outlined=False, dark=stints["compound"].isin(["WET", "SOFT", "INTERMEDIATE"]),
    )[["acronym", "compound", "start", "end", "age", "colour", "outlined", "dark"]]
    marks = pit_stops.assign(lap=pit_stops["lap_number"].astype(int),
                             seconds=pit_stops["pit_duration"].round(1).astype(object).where(pit_stops["pit_duration"].notna(), None))
    stints_by_driver = {name: group.drop(columns="acronym").to_dict("records") for name, group in bars.groupby("acronym")}
    pits_by_driver = {name: group[["lap", "seconds"]].to_dict("records") for name, group in marks.groupby("acronym")}
    colours = drivers.set_index("acronym")["team_colour"]
    order = table.assign(position=table["finish"].astype("string").fillna("–"))
    rows = [
        {"acronym": row.acronym, "position": row.position, "colour": colours.get(row.acronym, theme.FALLBACK_COLOUR),
         "stints": stints_by_driver.get(row.acronym, []), "pits": pits_by_driver.get(row.acronym, [])}
        for row in order.itertuples()
    ]
    used = [c for c in theme.COMPOUND_COLOURS if c in set(bars["compound"])]
    compounds = [{"name": c.capitalize(), "colour": theme.COMPOUND_COLOURS[c], "outlined": False} for c in used]
    return {"laps": int(bars["end"].max()), "drivers": rows, "compounds": compounds}


payload = timeline_payload()
with components.tile("timeline"):
    components.tile_heading(
        "Who ran which tyre, and when",
        "One row per driver in finishing order. Bars are stints, coloured by compound and labelled with their "
        "length in laps; thin ticks are pit stops. Hover for details.",
    )
    components.embed("strategy.html", payload, height=len(payload["drivers"]) * 25 + 90)

if not race:
    components.footer()
    st.stop()

chart, side = st.columns([1, 1])
with side, components.tile("deg-table", "gray"):
    components.tile_heading("Degradation per stint")
    fuel = st.toggle("Correct for fuel burn", value=False,
                     help=f"Adds {analysis.FUEL_SECONDS_PER_LAP} s for every lap already driven.")
    fuel_per_lap = analysis.FUEL_SECONDS_PER_LAP if fuel else 0.0
    own = laps.loc[laps["acronym"].isin(selection.drivers)]
    points = analysis.degradation_laps(own, fuel_per_lap).dropna(subset=["tyre_age"])
    fits = analysis.degradation(own, fuel_per_lap)
    if fits.empty:
        st.caption("No stint of the selected drivers has enough clean laps for a fit.")
    else:
        margin = (fits["ci_high"] - fits["ci_low"]) / 2
        show = pd.DataFrame({
            "Driver": fits["acronym"],
            "Stint": fits["stint_number"].astype(int).astype(str) + " " + fits["compound"].str.capitalize(),
            "Laps": fits["n"],
            "s per lap (95% CI)": fits["slope"].map("{:+.3f}".format) + " ± " + margin.map("{:.3f}".format),
            "R²": fits["r2"].map("{:.2f}".format),
        })
        components.table(show)
    st.caption(
        "Slope of a straight line through lap time against tyre age. If the 95% interval includes zero, the data "
        "cannot tell wear from noise. A low R² means tyre age explains little of the lap-time spread."
    )
    if fuel:
        st.caption(
            f"Assumption: the car gains a constant {analysis.FUEL_SECONDS_PER_LAP} s per lap as fuel burns off. "
            "That gain is added back, so the slope shows the tyres alone. The true value differs by track and car."
        )
    else:
        st.caption("Without the correction, fuel burn makes the car faster each lap and hides part of the tyre wear, "
                   "so slopes can even be negative.")

with chart, components.tile("deg-chart"):
    components.tile_heading(
        "Does the tyre get slower with age?",
        "Clean laps only, first lap of each stint left out. Point fill is the tyre colour, outline and line are the "
        "driver's team colour.",
    )
    if points.empty:
        st.caption("No clean laps to plot for the selected drivers.")
    else:
        components.animated_plot(charts.degradation_figure(points, fits, theme.driver_styles(drivers, selection.drivers)))

components.footer()
