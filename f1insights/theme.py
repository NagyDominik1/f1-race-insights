"""Design tokens, data colours, the Plotly template and the global CSS block.

Palette colours style the interface; team and tyre colours are data colours
and are kept separate. No Streamlit imports here.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

# --- interface palette -----------------------------------------------------
CANVAS = "#FBFBFD"
TILE = "#F2F2F5"
WHITE = "#FFFFFF"
INK = "#1D1D1F"
SECONDARY = "#6E6E73"
HAIRLINE = "#E3E3E8"
RED = "#E10600"  # accent only: calls to action, active states, one key number per view
MIDNIGHT = "#0B1E3F"
SKY = "#DCEBFA"
SAND = "#F3E9DC"
CARBON = "#2B2D31"

FONT = "Inter, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
FONT_URL = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"

# --- data colours ----------------------------------------------------------
COMPOUND_COLOURS = {
    "SOFT": "#E0262C",
    "MEDIUM": "#F7C600",
    "HARD": "#FFFFFF",
    "INTERMEDIATE": "#3DAA35",
    "WET": "#1E6FD9",
    "UNKNOWN": "#C4C4CC",
}
COMPOUND_OUTLINE = "#9A9AA2"  # HARD is white: it needs an outline on light backgrounds
FALLBACK_COLOUR = "#808080"
EXCLUDED_COLOUR = "#C4C4CC"
TEMPLATE_NAME = "f1insights"


def compound_colour(compound: str) -> str:
    """Tyre colour of a compound name (grey for unknown names)."""
    return COMPOUND_COLOURS.get(str(compound).upper(), COMPOUND_COLOURS["UNKNOWN"])


def driver_styles(drivers: pd.DataFrame, acronyms: list[str]) -> pd.DataFrame:
    """Colour and line dash per driver, indexed by acronym in the given order.

    Team-mates share a team colour, so the second driver of a colour gets a
    dashed line: series never rely on colour alone.
    """
    styles = drivers.drop_duplicates("acronym").set_index("acronym")[["team_colour"]]
    styles = styles.reindex(acronyms).rename(columns={"team_colour": "colour"})
    styles["colour"] = styles["colour"].fillna(FALLBACK_COLOUR)
    styles["dash"] = np.where(styles["colour"].duplicated(), "dash", "solid")
    return styles


def plotly_template() -> go.layout.Template:
    """Light template: ink text, thin axes, faint horizontal gridlines only."""
    axis = dict(
        showgrid=False, zeroline=False, showline=True, linecolor=HAIRLINE, linewidth=1,
        ticks="outside", tickcolor=HAIRLINE, ticklen=4,
        tickfont=dict(color=SECONDARY, size=12), title=dict(font=dict(color=SECONDARY, size=12)),
    )
    return go.layout.Template(layout=dict(
        font=dict(family=FONT, color=INK, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=[INK, RED, MIDNIGHT, "#8E8E93", "#3A7BD5", "#B0885A"],
        margin=dict(l=8, r=8, t=28, b=8),
        xaxis=axis,
        yaxis=axis | dict(showgrid=True, gridcolor="#EFEFF2", gridwidth=1, showline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text="",
                    font=dict(size=12, color=INK)),
        hoverlabel=dict(bgcolor=WHITE, bordercolor=HAIRLINE, font=dict(family=FONT, color=INK, size=12)),
        title=dict(font=dict(size=15, color=INK), x=0, xanchor="left"),
    ))


def register_plotly_template() -> None:
    """Register the template and make it the default for every figure."""
    pio.templates[TEMPLATE_NAME] = plotly_template()
    pio.templates.default = TEMPLATE_NAME


def css_variables() -> str:
    """The palette as CSS custom properties, shared by the app and the HTML components."""
    tokens = {
        "canvas": CANVAS, "tile": TILE, "white": WHITE, "ink": INK, "secondary": SECONDARY,
        "hairline": HAIRLINE, "red": RED, "midnight": MIDNIGHT, "sky": SKY, "sand": SAND,
        "carbon": CARBON,
    }
    lines = "".join(f"--{name}:{value};" for name, value in tokens.items())
    return f":root{{{lines}--font:{FONT};--ease:cubic-bezier(.2,.8,.2,1);}}"


def global_css() -> str:
    """One CSS block for the whole Streamlit app (bento tiles, type, navigation)."""
    return f"""
@import url('{FONT_URL}');
{css_variables()}
html, body, .stApp, [data-testid="stAppViewContainer"] {{ background: var(--canvas); }}
.stApp, .stApp p, .stApp li, .stApp label, .stApp button, .stApp input {{ font-family: var(--font); }}
.stMainBlockContainer {{ max-width: 1240px; padding-top: 4.5rem; padding-bottom: 3rem; }}
h1, h2, h3 {{ font-family: var(--font); color: var(--ink); letter-spacing: -0.022em; font-weight: 600; }}
h1 {{ font-size: clamp(2.2rem, 4.4vw, 3.5rem); letter-spacing: -0.035em; line-height: 1.04; font-weight: 700; padding: 0; }}
h2 {{ font-size: 1.75rem; }}
h3 {{ font-size: 1.2rem; padding-bottom: .2rem; }}
[data-testid="stHeader"] {{ background: rgba(251,251,253,.82); backdrop-filter: saturate(180%) blur(18px); border-bottom: 1px solid var(--hairline); }}
[data-testid="stTopNavLink"], [data-testid="stTopNavSection"] {{ font-weight: 500; }}

/* bento tiles: st.container(border=True, key="tile-<tone>-<name>") */
[class*="st-key-tile-"] {{ border: 0 !important; border-radius: 24px !important; padding: 1.5rem 1.6rem !important;
  background: var(--white); box-shadow: 0 0 0 1px var(--hairline); }}
[class*="st-key-tile-gray-"] {{ background: var(--tile); box-shadow: none; }}
[class*="st-key-tile-sand-"] {{ background: var(--sand); box-shadow: none; }}
[class*="st-key-tile-sky-"] {{ background: var(--sky); box-shadow: none; }}
[class*="st-key-tile-midnight-"] {{ background: var(--midnight); box-shadow: none; }}
[class*="st-key-tile-midnight-"] :is(h1,h2,h3,p,li,span,label) {{ color: #fff; }}
.tile-sub {{ color: var(--secondary); font-size: .95rem; margin: -.35rem 0 .6rem; max-width: 68ch; }}

/* page header */
.gp-title {{ font-size: clamp(2rem, 4vw, 3.25rem); font-weight: 700; letter-spacing: -0.035em; line-height: 1.05; color: var(--ink); margin: .2rem 0 .35rem; }}
.gp-meta {{ color: var(--secondary); font-size: 1.05rem; margin: 0; }}
.gp-meta strong {{ color: var(--ink); font-weight: 600; }}
.badge {{ display: inline-block; margin-left: .6rem; padding: .16rem .6rem; border-radius: 999px; background: var(--sand);
  color: #6B4E2E; font-size: .78rem; font-weight: 600; vertical-align: middle; }}
.app-footer {{ color: var(--secondary); font-size: .82rem; margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--hairline); }}
.app-footer a {{ color: var(--ink); }}

/* controls */
.stButton > button, [data-testid="stPopover"] button, [data-testid="stPageLink"] a {{ border-radius: 999px; font-weight: 500; }}
.stButton > button[kind="primary"] {{ background: var(--red); border-color: var(--red); }}
.stButton > button {{ transition: transform .25s var(--ease), box-shadow .25s var(--ease); }}
.stButton > button:hover {{ transform: translateY(-1px); }}
:focus-visible {{ outline: 2px solid var(--red); outline-offset: 2px; }}
[data-testid="stDataFrame"] {{ border-radius: 14px; overflow: hidden; }}
[data-testid="stCaptionContainer"] {{ color: var(--secondary); }}
iframe[data-testid="stIFrame"] {{ border-radius: 24px; }}
@media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ transition: none !important; animation: none !important; }} }}
"""
