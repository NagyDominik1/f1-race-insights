"""Pace: lap time distribution of the selected drivers on clean laps."""

import pandas as pd
import streamlit as st

from f1insights import analysis, theme
from ui import charts, components, loaders

selection = components.page_header()
key, race = selection.session_key, components.is_race(selection)

with components.loading("Loading lap times"):
    laps = loaders.analysed_laps(key, race)
    drivers = loaders.drivers(key)

own = laps.loc[laps["acronym"].isin(selection.drivers)]
if not own["is_clean"].any():
    components.empty_state("There are no clean laps for the selected drivers in this session.")

styles = theme.driver_styles(drivers, selection.drivers)
chart, side = st.columns([2, 1])
with chart, components.tile("distribution"):
    components.tile_heading(
        "How fast, and how consistently",
        "Every point is one clean lap. The box spans the middle half of a driver's laps and the line inside is the median.",
    )
    show_excluded = st.toggle("Show the excluded laps in grey", value=False)
    components.plot(charts.pace_distribution(own, styles, show_excluded), "pace")
    if show_excluded:
        st.caption("Excluded laps far slower than the clean ones, such as pit stops, fall outside the axis.")

with side, components.tile("stats", "gray"):
    components.tile_heading("Clean-lap statistics")
    stats_table = analysis.pace_stats(own)
    show = pd.DataFrame({
        "Laps": stats_table["n"].astype(str).to_numpy(),
        "Median": stats_table["median"].map(analysis.format_lap_time).to_numpy(),
        "IQR (s)": stats_table["iqr"].map("{:.3f}".format).to_numpy(),
        "Std (s)": stats_table["std"].map("{:.3f}".format).to_numpy(),
        "Fastest": stats_table["fastest"].map(analysis.format_lap_time).to_numpy(),
    }, index=stats_table["acronym"].rename("")).T
    components.table(show, index=True)
    st.caption(
        "Median and IQR (the width of the middle 50% of laps) are used instead of mean and standard deviation "
        "because one slow lap behind traffic barely moves them. The mean would shift with every outlier."
    )

with side, components.tile("filtered", "sand"):
    components.tile_heading("What was filtered out")
    reference = "the driver's median" if race else "the driver's fastest lap"
    counts = own.loc[~own["is_clean"]].groupby(["reason", "acronym"]).size().unstack(fill_value=0)
    counts = counts.reindex(columns=selection.drivers, fill_value=0).rename_axis("Reason").reset_index()
    if counts.empty:
        st.caption("Nothing: every lap of the selected drivers counts as clean.")
    else:
        components.table(counts)
    st.caption(f"A lap slower than 107% of {reference} counts as not representative.")

components.footer()
