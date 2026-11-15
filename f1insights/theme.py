"""Design tokens, data colours, the Plotly template and the CSS blocks.

Two surfaces: the landing page is light (soft whites, never pure white), the
Analytics and Races pages are dark with glass cards. Team and tyre colours are
data colours and stay the same everywhere. No Streamlit imports here.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

# --- light palette (landing page) ------------------------------------------
CANVAS = "#F5F5F7"
TILE = "#E8E8ED"
WHITE = "#FBFBFD"  # the lightest surface; pure #FFFFFF is not used for large areas
INK = "#1D1D1F"
SECONDARY = "#63636A"
HAIRLINE = "#DCDCE1"
RED = "#E10600"  # accent only: calls to action, active states, one key number per view
MIDNIGHT = "#0B1E3F"
SKY = "#DCEBFA"
SAND = "#F3E9DC"
CARBON = "#2B2D31"

# --- dark palette (Analytics and Races pages) -------------------------------
TEXT = "#F5F5F7"
MUTED = "#A1A1A6"
LINE = "rgba(255,255,255,0.08)"
LINE_STRONG = "rgba(255,255,255,0.16)"
GRID = "rgba(255,255,255,0.06)"
SECTIONS = {
    # page background, glass card, raised card (a step lighter, for emphasis)
    "analytics": {"page": "#071124", "card": "#0E182D", "raised": "#15223C"},  # midnight-tinted
    "races": {"page": "#0A0A0C", "card": "#16171A", "raised": "#1F2024"},      # graphite
}

FONT = "Inter, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
FONT_URL = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"

# --- data colours ----------------------------------------------------------
COMPOUND_COLOURS = {
    "SOFT": "#E0262C",
    "MEDIUM": "#F7C600",
    "HARD": "#FFFFFF",  # on the dark pages white needs no outline
    "INTERMEDIATE": "#3DAA35",
    "WET": "#1E6FD9",
    "UNKNOWN": "#8E8E93",
}
FALLBACK_COLOUR = "#808080"
EXCLUDED_COLOUR = "#6E6E73"
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
    """Dark template: transparent background, light text, thin axes, faint horizontal grid."""
    axis = dict(
        showgrid=False, zeroline=False, showline=True, linecolor=LINE_STRONG, linewidth=1, automargin=True,
        ticks="outside", tickcolor=LINE_STRONG, ticklen=4,
        tickfont=dict(color=MUTED, size=12), title=dict(font=dict(color=MUTED, size=12)),
    )
    return go.layout.Template(layout=dict(
        font=dict(family=FONT, color=TEXT, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=[TEXT, RED, "#7FB0FF", MUTED, "#F7C600", "#3DAA35"],
        margin=dict(l=8, r=8, t=28, b=8),
        xaxis=axis,
        yaxis=axis | dict(showgrid=True, gridcolor=GRID, gridwidth=1, showline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text="",
                    font=dict(size=12, color=TEXT)),
        hoverlabel=dict(bgcolor="#1F2024", bordercolor=LINE_STRONG, font=dict(family=FONT, color=TEXT, size=12)),
        title=dict(font=dict(size=15, color=TEXT), x=0, xanchor="left"),
    ))


def register_plotly_template() -> None:
    """Register the template and make it the default for every figure."""
    pio.templates[TEMPLATE_NAME] = plotly_template()
    pio.templates.default = TEMPLATE_NAME


def css_variables(section: str | None = None) -> str:
    """The palette as CSS custom properties.

    Without a section these are the light tokens of the landing page. With a
    section they are its dark tokens under the same names, so the HTML
    components (which only use the variables) follow the page they sit on.
    """
    tokens = {
        "canvas": CANVAS, "tile": TILE, "white": WHITE, "ink": INK, "secondary": SECONDARY,
        "hairline": HAIRLINE, "red": RED, "midnight": MIDNIGHT, "sky": SKY, "sand": SAND,
        "carbon": CARBON, "on-ink": "#FFFFFF", "soft": "rgba(120,120,128,.14)",
    }
    if section:
        dark = SECTIONS[section]
        tokens |= {
            "canvas": dark["page"], "tile": dark["raised"], "white": dark["card"], "ink": TEXT,
            "secondary": MUTED, "hairline": LINE, "sky": dark["raised"], "sand": dark["raised"],
            "on-ink": INK, "soft": "rgba(255,255,255,.08)",
        }
    lines = "".join(f"--{name}:{value};" for name, value in tokens.items())
    return f":root{{{lines}--font:{FONT};--ease:cubic-bezier(.2,.8,.2,1);}}"


def global_css() -> str:
    """Base CSS of every page (type, tiles, header, controls).

    The Inter font itself is loaded through .streamlit/config.toml: st.html
    drops style blocks that contain an @import rule or angle brackets.
    """
    return f"""
{css_variables()}
html, body, .stApp, [data-testid="stAppViewContainer"] {{ background: var(--canvas); }}
.stApp, .stApp p, .stApp li, .stApp label, .stApp button, .stApp input {{ font-family: var(--font); }}
.stMainBlockContainer {{ max-width: 1240px; padding-top: 4.5rem; padding-bottom: 3rem; }}
h1, h2, h3 {{ font-family: var(--font); color: var(--ink); letter-spacing: -0.022em; font-weight: 600; }}
h1 {{ font-size: clamp(2.2rem, 4.4vw, 3.5rem); letter-spacing: -0.035em; line-height: 1.04; font-weight: 700; padding: 0; }}
h2 {{ font-size: 1.75rem; }}
h3 {{ font-size: 1.2rem; padding-bottom: .2rem; }}
[data-testid="stHeader"] {{ background: rgba(245,245,247,.82); backdrop-filter: saturate(180%) blur(18px); border-bottom: 1px solid var(--hairline); }}
[data-testid="stTopNavLink"], [data-testid="stTopNavSection"] {{ font-weight: 500; }}

/* bento tiles: st.container(border=True) with a key that starts with "tile-" plus the tone */
[class*="st-key-tile-"] {{ border: 0 !important; border-radius: 24px !important; padding: 1.5rem 1.6rem !important;
  background: var(--white); box-shadow: 0 0 0 1px var(--hairline); }}
.tile-sub {{ color: var(--secondary); font-size: .95rem; margin: -.35rem 0 .6rem; max-width: 68ch; }}

/* page header */
.gp-title {{ font-size: clamp(2rem, 4vw, 3.25rem); font-weight: 700; letter-spacing: -0.035em; line-height: 1.05; color: var(--ink); margin: .2rem 0 .35rem; }}
.gp-meta {{ color: var(--secondary); font-size: 1.05rem; margin: 0; }}
.gp-meta strong {{ color: var(--ink); font-weight: 600; }}
.badge {{ display: inline-block; margin-left: .6rem; padding: .16rem .6rem; border-radius: 999px; font-size: .78rem; font-weight: 600; vertical-align: middle; }}
.accent-bar {{ display: block; width: 46px; height: 6px; background: var(--red); transform: skewX(-24deg); margin: 0 0 .75rem 3px; }}
.app-footer {{ font-size: .82rem; margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--hairline); }}
.ri-logo {{ height: 28px; width: auto; display: block; }}

/* controls */
.stButton > button, [data-testid="stPopover"] button, [data-testid="stPageLink"] a {{ border-radius: 999px; font-weight: 500; }}
.stButton > button[kind="primary"] {{ background: var(--red); border-color: var(--red); }}
.stButton > button {{ transition: transform .25s var(--ease), box-shadow .25s var(--ease); }}
.stButton > button:hover {{ transform: translateY(-1px); }}
:focus-visible {{ outline: 2px solid var(--red); outline-offset: 2px; }}
iframe[data-testid="stIFrame"] {{ border-radius: 24px; }}
@media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ transition: none !important; animation: none !important; }} }}
"""


def section_css(section: str) -> str:
    """CSS of a dark section page: page colour, glass cards, light text, dark controls, hero backdrop."""
    dark = SECTIONS[section]
    main = ".stMainBlockContainer"
    active = ':is([kind$="Active"], [aria-checked="true"], [aria-pressed="true"])'
    return f"""
html, body, .stApp, [data-testid="stAppViewContainer"] {{ background: {dark["page"]}; }}
[data-testid="stHeader"] {{ background: rgba(10,10,12,.72); backdrop-filter: saturate(160%) blur(18px); border-bottom: 1px solid {LINE}; }}
[data-testid="stHeader"] :is(p, span, a) {{ color: {TEXT}; }}
[data-testid="stHeader"] svg {{ fill: {TEXT}; color: {TEXT}; }}
[data-testid="stHeader"] :is([data-testid="stTopNavLink"], [data-testid="stTopNavSection"]):hover {{ background: rgba(255,255,255,.1); }}

{main} :is(p, span, label, li, h1, h2, h3, h4, strong, em, td, th, small, a) {{ color: {TEXT}; }}
{main} :is(.tile-sub, .gp-meta, .app-footer, [data-testid="stCaptionContainer"] :is(p, span)) {{ color: {MUTED}; }}
{main} .gp-meta strong, {main} .gp-title {{ color: {TEXT}; }}
{main} .badge {{ background: rgba(255,255,255,.1); color: {TEXT}; }}
{main} .app-footer {{ border-top-color: {LINE}; }}
{main} code {{ background: rgba(255,255,255,.1); color: {TEXT}; }}
{main} blockquote {{ border-left-color: {RED}; }}

/* dark glass cards: one hairline, a soft highlight along the top edge */
{main} [class*="st-key-tile-"] {{ background: {dark["card"]}; box-shadow: inset 0 1px 0 rgba(255,255,255,.07), 0 0 0 1px {LINE}; }}
{main} :is([class*="st-key-tile-gray-"], [class*="st-key-tile-sand-"], [class*="st-key-tile-sky-"], [class*="st-key-tile-carbon-"]) {{
  background: {dark["raised"]}; }}

/* controls on dark */
{main} :is(.stButton > button[kind="secondary"], [data-testid="stPopover"] button, [data-testid="stButtonGroup"] button) {{
  background: rgba(255,255,255,.07); border-color: {LINE_STRONG}; }}
{main} [data-testid="stButtonGroup"] button{active} {{ background: {RED}; border-color: {RED}; }}
{main} [data-testid="stPageLink"] a:hover {{ background: rgba(255,255,255,.1); }}
{main} [data-testid="stCheckbox"] label:has(input:not(:checked)) > div:nth-child(2) {{ background: rgba(255,255,255,.22); }}

/* plain tables instead of the light data grid */
.ri-table-wrap.scroll {{ max-height: 292px; overflow-y: auto; }}
.ri-table {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
.ri-table th {{ text-align: left; font-size: .78rem; font-weight: 500; color: {MUTED}; padding: 6px 10px 8px 0; border-bottom: 1px solid {LINE_STRONG}; }}
.ri-table td {{ font-size: .9rem; padding: 7px 10px 7px 0; border-bottom: 1px solid {LINE}; }}
.ri-table tr:last-child td {{ border-bottom: 0; }}
.ri-table tbody th {{ color: {TEXT}; font-weight: 600; font-size: .9rem; border-bottom: 1px solid {LINE}; }}

/* hero: the page header on top of an abstract backdrop drawn from the session's data */
[class*="st-key-hero-"] {{ position: relative; padding: 2.4rem .25rem 1.3rem !important; min-height: 250px; justify-content: flex-end; }}
[class*="st-key-hero-"] > [data-testid="stElementContainer"]:first-child {{ position: static; }}
.hero-art {{ position: absolute; inset: -4.5rem 0 -150px 0; pointer-events: none; z-index: 0;
  -webkit-mask-image: radial-gradient(ellipse 78% 88% at 58% 36%, #000 30%, transparent 100%);
  mask-image: radial-gradient(ellipse 78% 88% at 58% 36%, #000 30%, transparent 100%); }}
.hero-art canvas {{ width: 100%; height: 100%; display: block; }}
[class*="st-key-hero-"] > :not(:first-child) {{ position: relative; z-index: 2; }}
/* everything after the hero sits above its backdrop */
[class*="st-key-hero-"] ~ * {{ position: relative; z-index: 1; }}
@media (max-width: 640px) {{ [class*="st-key-hero-"] {{ padding-top: 1.2rem !important; min-height: 0; }} }}
"""
