"""Overview: the session in five numbers, the position chart and an auto-written race story."""

import pandas as pd
import streamlit as st

from f1insights import analysis, theme
from ui import charts, components, loaders

selection = components.page_header()
key, race = selection.session_key, components.is_race(selection)

with components.loading("Loading the session"):
    laps = loaders.analysed_laps(key, race)
    drivers = loaders.drivers(key)
    positions = loaders.positions(key)
    results = loaders.results(key)
    pit_stops = loaders.pit_stops(key)
    periods = analysis.neutralisations(loaders.race_control(key))

quickest = analysis.fastest_lap(laps)
if quickest is None:
    components.empty_state("OpenF1 has no lap times for this session yet. It may not have taken place.")

styles = theme.driver_styles(drivers, drivers["acronym"].tolist())
fastest_tile = {
    "label": "Fastest lap", "number": float(quickest["LapTimeSeconds"]), "format": "laptime", "accent": True,
    "note": f"{quickest['acronym']}, lap {quickest['lap_number']}",
}


def race_overview() -> None:
    table = analysis.classification(laps, positions, results)
    stats_table = analysis.pace_stats(laps)
    fits = analysis.degradation(laps)
    winner = table.iloc[0]
    kinds = periods["kind"].value_counts()
    if periods.empty:
        neutral_note = "Green from start to finish"
    else:
        names = {"SC": "safety car", "VSC": "virtual safety car", "RED": "red flag"}
        neutral_note = ", ".join(f"{count} {names[kind]}" for kind, count in kinds.items())
    movers = table.loc[table["classified"]].dropna(subset=["gained"])
    tiles = [
        {"label": "Winner", "text": winner["acronym"], "white": True,
         "note": f"from P{winner['grid']} on the grid" if pd.notna(winner["grid"]) else ""},
        fastest_tile,
        {"label": "Pit stops", "number": len(pit_stops), "note": f"by {pit_stops['driver_number'].nunique()} drivers"},
        {"label": "Safety car and red flag periods", "number": len(periods), "note": neutral_note},
    ]
    if not movers.empty and movers["gained"].max() > 0:
        mover = movers.loc[movers["gained"].idxmax()]
        tiles.append({"label": "Biggest mover", "number": int(mover["gained"]), "prefix": "+",
                      "note": f"{mover['acronym']}, P{mover['grid']} to P{mover['finish']}"})
    components.embed("kpi.html", {"tiles": tiles}, height=150)

    chart, story = st.columns([2, 1])
    with chart, components.tile("bump"):
        components.tile_heading(
            "Who was where, lap by lap",
            "Positions at the end of each lap, starting from the grid. Your selected drivers are drawn bold; "
            "team-mates share a colour, so the second one is dashed.",
        )
        by_lap = analysis.position_by_lap(laps, positions)
        if by_lap.empty:
            st.caption("OpenF1 has no position data for this session.")
        else:
            components.plot(charts.bump_chart(by_lap, styles.reindex(table["acronym"]), selection.drivers), "bump")
    with story, components.tile("story", "sand"):
        components.tile_heading("The race in a few sentences")
        sentences = analysis.race_story(table, stats_table, fits, pit_stops, laps)
        st.markdown("\n\n".join(sentences))
        st.caption("Written by fixed templates from the numbers on these pages, not by a language model. "
                   "Pace and degradation use clean laps only; see Methodology.")
    with story, components.tile("order", "gray"):
        components.tile_heading("Classification")
        show = table.assign(
            Pos=table["finish"].astype("string").fillna("DNF"), Driver=table["acronym"],
            Grid=table["grid"], Laps=table["laps"],
        )[["Pos", "Driver", "Grid", "Laps"]]
        st.dataframe(show, hide_index=True, height=282)


def qualifying_overview() -> None:
    timed = laps.dropna(subset=["LapTimeSeconds"])
    best = timed.loc[timed.groupby("acronym")["LapTimeSeconds"].idxmin(), ["acronym", "LapTimeSeconds", "lap_number"]]
    best = best.sort_values("LapTimeSeconds").assign(gap=lambda d: d["LapTimeSeconds"] - d["LapTimeSeconds"].min())
    tiles = [
        {"label": "Fastest driver", "text": best.iloc[0]["acronym"], "white": True, "note": "best lap of the session"},
        fastest_tile,
    ]
    if len(best) > 1:
        tiles.append({"label": "Margin to second", "number": float(best.iloc[1]["gap"]), "decimals": 3,
                      "suffix": " s", "note": f"over {best.iloc[1]['acronym']}"})
    tiles.append({"label": "Timed laps", "number": len(timed), "note": f"by {timed['acronym'].nunique()} drivers"})
    components.embed("kpi.html", {"tiles": tiles}, height=150)
    with components.tile("gaps"):
        components.tile_heading("Gap to the fastest lap", "Each driver's best lap of the session, slowest at the top.")
        components.plot(charts.gap_to_fastest(best, styles), "gaps")


if race:
    race_overview()
else:
    qualifying_overview()
components.footer()
