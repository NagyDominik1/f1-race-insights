"""Plotly figure builders. They only arrange already-computed DataFrames into traces."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from f1insights import theme
from f1insights.analysis import format_lap_time

SYMBOLS = ["circle", "diamond", "square", "triangle-up", "cross", "x"]


def _lap_ticks(low: float, high: float) -> dict:
    """Axis ticks labelled as lap times (m:ss.s) instead of raw seconds."""
    step = max(0.5, round((high - low) / 6 * 2) / 2)
    values = np.arange(np.floor(low), np.ceil(high) + step, step)
    return dict(tickmode="array", tickvals=values, ticktext=[format_lap_time(v)[:-2] for v in values])


def bump_chart(by_lap: pd.DataFrame, styles: pd.DataFrame, highlighted: list[str]) -> go.Figure:
    """Position of every driver lap by lap; the play button redraws the race from the grid."""
    wide = by_lap.pivot(index="lap_number", columns="acronym", values="position").reindex(columns=styles.index)
    laps = wide.index.to_numpy()
    fig = go.Figure()
    for name in wide.columns:
        strong = name in highlighted
        fig.add_scatter(
            x=laps, y=wide[name], name=name, mode="lines", connectgaps=False,
            line=dict(color=styles.loc[name, "colour"], dash=styles.loc[name, "dash"], width=3.2 if strong else 1.4),
            opacity=1 if strong else 0.5,
            hovertemplate=f"<b>{name}</b> P%{{y}} after lap %{{x}}<extra></extra>",
        )
    last = wide.apply(lambda column: column.last_valid_index())
    final = pd.Series([wide.loc[last[name], name] for name in wide.columns], index=wide.columns)
    fig.add_scatter(
        x=last.to_numpy() + 0.8, y=final, text=wide.columns, mode="text", textposition="middle right",
        textfont=dict(size=11, color=theme.INK), hoverinfo="skip", showlegend=False, cliponaxis=False,
    )
    traces = list(range(len(wide.columns)))
    fig.frames = [
        go.Frame(name=str(lap), traces=traces,
                 data=[go.Scatter(x=laps[: i + 1], y=wide[name].to_numpy()[: i + 1]) for name in wide.columns])
        for i, lap in enumerate(laps)
    ]
    play = dict(frame=dict(duration=130, redraw=False), transition=dict(duration=0), mode="immediate", fromcurrent=False)
    fig.update_layout(
        height=560, showlegend=False, margin=dict(l=8, r=30, t=46, b=8),
        xaxis=dict(title="Lap", range=[0, laps.max() + 4.5]),
        yaxis=dict(title="Position", range=[len(wide.columns) + 0.6, 0.4], tickmode="linear", tick0=1, dtick=1,
                   showgrid=False, automargin=True, ticks=""),
        updatemenus=[dict(
            type="buttons", showactive=False, x=0, y=1.1, xanchor="left", yanchor="top",
            bgcolor=theme.WHITE, bordercolor=theme.HAIRLINE, font=dict(size=12, color=theme.INK),
            buttons=[dict(label="▶  Play the race", method="animate", args=[None, play])],
        )],
    )
    return fig


def gap_to_fastest(best: pd.DataFrame, styles: pd.DataFrame) -> go.Figure:
    """Qualifying order: each driver's best lap as a gap to the fastest (bars labelled with the gap)."""
    best = best.sort_values("gap", ascending=False)
    fig = go.Figure(go.Bar(
        x=best["gap"], y=best["acronym"], orientation="h",
        marker=dict(color=styles.reindex(best["acronym"])["colour"].tolist(), line=dict(color=theme.HAIRLINE, width=1)),
        text=[f"+{gap:.3f}" if gap > 0 else format_lap_time(time) for gap, time in zip(best["gap"], best["LapTimeSeconds"])],
        textposition="outside", textfont=dict(size=11, color=theme.SECONDARY), cliponaxis=False,
        hovertemplate="<b>%{y}</b> +%{x:.3f} s<extra></extra>",
    ))
    fig.update_layout(height=max(320, 26 * len(best) + 60), xaxis=dict(title="Gap to the fastest lap (s)"),
                      yaxis=dict(showgrid=False, title=""), margin=dict(l=8, r=60, t=10, b=8))
    return fig


def pace_distribution(laps: pd.DataFrame, styles: pd.DataFrame, show_excluded: bool) -> go.Figure:
    """Box plot with every clean lap as a point per driver; excluded laps optionally in grey."""
    fig = go.Figure()
    clean = laps.loc[laps["is_clean"]]
    for name in styles.index:
        own = clean.loc[clean["acronym"] == name]
        colour = styles.loc[name, "colour"]
        fig.add_box(
            x=own["acronym"], y=own["LapTimeSeconds"], name=name, boxpoints="all", jitter=0.55, pointpos=0,
            line=dict(color=colour, width=1.6), fillcolor="rgba(0,0,0,0)", whiskerwidth=0.4,
            marker=dict(color=colour, size=5, opacity=0.6, line=dict(color=theme.INK, width=0.4)),
            customdata=own["lap_number"], hovertemplate="lap %{customdata}: %{y:.3f} s<extra>" + name + "</extra>",
        )
    low, high = clean["LapTimeSeconds"].min(), clean["LapTimeSeconds"].max()
    if show_excluded:
        out = laps.loc[~laps["is_clean"] & laps["LapTimeSeconds"].notna() & laps["acronym"].isin(styles.index)]
        high = min(out["LapTimeSeconds"].max(), high * 1.09) if not out.empty else high
        fig.add_box(
            x=out["acronym"], y=out["LapTimeSeconds"], name="Excluded", boxpoints="all", jitter=0.55, pointpos=0,
            line=dict(color="rgba(0,0,0,0)"), fillcolor="rgba(0,0,0,0)",
            marker=dict(color=theme.EXCLUDED_COLOUR, size=6, symbol="x-thin", line=dict(color="#8E8E93", width=1.2)),
            customdata=np.stack([out["lap_number"], out["reason"]], axis=-1) if not out.empty else None,
            hovertemplate="lap %{customdata[0]}: %{y:.3f} s<br>excluded: %{customdata[1]}<extra></extra>",
        )
    pad = (high - low) * 0.06 + 0.1
    fig.update_layout(height=470, showlegend=False, boxmode="overlay",
                      yaxis=dict(title="Lap time", range=[low - pad, high + pad], **_lap_ticks(low, high)),
                      xaxis=dict(title="", categoryorder="array", categoryarray=list(styles.index)))
    return fig


def degradation_figure(points: pd.DataFrame, fits: pd.DataFrame, styles: pd.DataFrame) -> go.Figure:
    """Lap time against tyre age: points filled with the tyre colour, one fitted line per stint.

    The lines start collapsed at their first point; the frame "full" holds the
    real lines, so the component can animate them in.
    """
    fig = go.Figure()
    for i, name in enumerate(styles.index):
        own = points.loc[points["acronym"] == name]
        fig.add_scatter(
            x=own["tyre_age"], y=own["fit_seconds"], mode="markers", name=name,
            marker=dict(size=9, symbol=SYMBOLS[i % len(SYMBOLS)], color=own["compound"].map(theme.compound_colour),
                        line=dict(color=styles.loc[name, "colour"], width=2)),
            customdata=np.stack([own["lap_number"], own["compound"]], axis=-1) if not own.empty else None,
            hovertemplate=f"<b>{name}</b> lap %{{customdata[0]}} (%{{customdata[1]}})<br>"
                          "tyre age %{x}: %{y:.3f} s<extra></extra>",
        )
    first_line = len(fig.data)
    full = []
    for fit in fits.itertuples():
        x = np.array([fit.age_min, fit.age_max])
        y = fit.intercept + fit.slope * x
        line = dict(color=styles.loc[fit.acronym, "colour"], dash=styles.loc[fit.acronym, "dash"], width=3)
        fig.add_scatter(
            x=[x[0], x[0]], y=[y[0], y[0]], mode="lines", line=line, showlegend=False,
            hovertemplate=f"<b>{fit.acronym}</b> {fit.compound}: {fit.slope:+.3f} s/lap<extra></extra>",
        )
        full.append(go.Scatter(x=x, y=y))
    fig.frames = [go.Frame(name="full", data=full, traces=list(range(first_line, first_line + len(full))))]
    low, high = points["fit_seconds"].min(), points["fit_seconds"].max()
    fig.update_layout(height=450, xaxis=dict(title="Tyre age (laps)"),
                      yaxis=dict(title="Lap time", **_lap_ticks(low, high)), margin=dict(l=8, r=8, t=40, b=8))
    return fig


def delta_figure(deltas: pd.DataFrame, first: str, second: str, styles: pd.DataFrame,
                 median: float, low: float, high: float) -> go.Figure:
    """Per-lap gap between two drivers; bars point towards the faster driver."""
    fig = go.Figure()
    for name, mask, pattern in [(first, deltas["delta"] < 0, ""), (second, deltas["delta"] >= 0, "/")]:
        same_colour = styles.loc[first, "colour"] == styles.loc[second, "colour"]
        fig.add_bar(
            x=deltas.loc[mask, "lap_number"], y=deltas.loc[mask, "delta"], name=f"{name} faster",
            marker=dict(color=styles.loc[name, "colour"], line=dict(color=theme.INK, width=0.5),
                        pattern=dict(shape=pattern if same_colour else "", fgcolor=styles.loc[name, "colour"],
                                     bgcolor=theme.WHITE, fillmode="replace", size=5)),
            hovertemplate=f"lap %{{x}}: {name} faster by %{{customdata:.3f}} s<extra></extra>",
            customdata=deltas.loc[mask, "delta"].abs(),
        )
    fig.add_hrect(y0=low, y1=high, fillcolor=theme.INK, opacity=0.07, line_width=0)
    fig.add_hline(y=median, line=dict(color=theme.INK, width=1.5, dash="dot"),
                  annotation_text=f"median {median:+.3f} s", annotation_position="top right",
                  annotation_font=dict(size=11, color=theme.INK))
    fig.update_layout(height=420, bargap=0.15, xaxis=dict(title="Lap"),
                      yaxis=dict(title=f"{first} − {second} (s)", zeroline=True, zerolinecolor=theme.HAIRLINE))
    return fig


def sector_figure(table: pd.DataFrame, first: str, second: str, styles: pd.DataFrame) -> go.Figure:
    """Gap per sector of the two best laps; the label names the faster driver."""
    sectors = table.loc[table["part"] != "Lap"].iloc[::-1]
    faster = np.where(sectors["gap"] < 0, first, second)
    fig = go.Figure(go.Bar(
        x=sectors["gap"], y=sectors["part"], orientation="h",
        marker=dict(color=styles.reindex(faster)["colour"].tolist(), line=dict(color=theme.INK, width=0.5)),
        text=[f"{name} by {abs(gap):.3f} s" for name, gap in zip(faster, sectors["gap"])],
        textposition="outside", cliponaxis=False, textfont=dict(size=12, color=theme.INK),
        hovertemplate="%{y}: %{text}<extra></extra>",
    ))
    span = max(sectors["gap"].abs().max() * 1.9, 0.05)
    fig.update_layout(height=250, xaxis=dict(title=f"{first} − {second} (s)", range=[-span, span], zeroline=True,
                                             zerolinecolor=theme.HAIRLINE),
                      yaxis=dict(title="", showgrid=False))
    return fig


def speed_trace(first_lap: pd.DataFrame, second_lap: pd.DataFrame, first: str, second: str,
                styles: pd.DataFrame) -> go.Figure:
    """Speed of two laps against lap distance."""
    fig = go.Figure()
    for name, lap in [(first, first_lap), (second, second_lap)]:
        fig.add_scatter(
            x=lap["fraction"] * 100, y=lap["speed"], name=name, mode="lines",
            line=dict(color=styles.loc[name, "colour"], dash=styles.loc[name, "dash"], width=2.2),
            hovertemplate=f"<b>{name}</b> %{{y:.0f}} km/h at %{{x:.0f}}%<extra></extra>",
        )
    fig.update_layout(height=340, hovermode="x unified", xaxis=dict(title="Lap distance (%)", range=[0, 100]),
                      yaxis=dict(title="Speed (km/h)"), margin=dict(l=8, r=8, t=40, b=8))
    return fig


def delta_trace(first_lap: pd.DataFrame, second_lap: pd.DataFrame, first: str, second: str,
                styles: pd.DataFrame) -> go.Figure:
    """Running time gap along the lap, filled towards the driver who is ahead."""
    gap = first_lap["t"] - second_lap["t"]
    x = first_lap["fraction"] * 100
    fig = go.Figure()
    for name, part in [(first, gap.clip(upper=0)), (second, gap.clip(lower=0))]:
        colour = styles.loc[name, "colour"]
        fig.add_scatter(x=x, y=part, mode="lines", line=dict(width=0), fill="tozeroy", name=f"{name} ahead",
                        fillcolor=f"rgba({int(colour[1:3], 16)},{int(colour[3:5], 16)},{int(colour[5:7], 16)},0.28)",
                        fillpattern=dict(shape="/" if styles.loc[name, "dash"] == "dash" else ""), hoverinfo="skip")
    fig.add_scatter(x=x, y=gap, mode="lines", line=dict(color=theme.INK, width=2), showlegend=False,
                    hovertemplate=f"{first} − {second}: %{{y:+.3f}} s at %{{x:.0f}}%<extra></extra>")
    fig.update_layout(height=340, xaxis=dict(title="Lap distance (%)", range=[0, 100]),
                      yaxis=dict(title=f"{first} − {second} (s)", zeroline=True, zerolinecolor=theme.HAIRLINE),
                      margin=dict(l=8, r=8, t=40, b=8))
    return fig
