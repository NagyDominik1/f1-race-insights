"""Reusable UI pieces: global CSS, bento tiles, the page header and HTML components."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from f1insights import theme
from f1insights.openf1 import OpenF1Error
from ui import decor, state

TEMPLATE_DIR = Path(__file__).parent / "templates"
REPO_URL = "https://github.com/NagyDominik1/f1-race-insights"
DISCLAIMER = "Unofficial project. Data from OpenF1. Not affiliated with Formula 1."
RACE_SESSIONS = ("Race", "Sprint")
PLOT_CONFIG = {"displayModeBar": False, "responsive": True}
# plays the frame "full" once after load; with reduced motion it jumps straight to it
ANIMATE_IN = """
const gd = document.getElementById('{plot_id}');
const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
const ms = still ? 0 : 900;
setTimeout(() => Plotly.animate(gd, ['full'], {frame: {duration: ms, redraw: false},
  transition: {duration: ms, easing: 'cubic-out'}, mode: 'immediate'}), still ? 0 : 350);
"""


def inject_css(extra: str = "") -> None:
    """The single style block of a page (global CSS + optional page CSS) and the Plotly template.

    Streamlit keeps only one style-only st.html per run, so every page calls this exactly once.
    """
    theme.register_plotly_template()
    st.html(f"<style>{theme.global_css()}{extra}</style>")


@lru_cache
def template_text(name: str) -> str:
    """Raw text of a file in ui/templates."""
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def render_template(name: str, payload: dict) -> str:
    """Fill an HTML template with the design tokens, the shared car drawing and JSON data."""
    blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    head = f"@import url('{theme.FONT_URL}');{theme.css_variables(st.session_state.get('section'))}"
    html = template_text(name).replace("/*__TOKENS__*/", head).replace("/*__CAR__*/", template_text("car.js"))
    return html.replace("__DATA__", blob)


def embed(name: str, payload: dict, height: int | str = "content") -> None:
    """Show a self-contained HTML/JS component in an iframe.

    st.iframe is the successor of the deprecated st.components.v1.html.
    """
    st.iframe(render_template(name, payload), height=height)


def tile(name: str, tone: str = "white"):
    """A bento tile: a rounded container styled by the global CSS (tone = palette name)."""
    return st.container(border=True, key=f"tile-{tone}-{name}")


def tile_heading(title: str, sub: str = "") -> None:
    st.html(f"<h3>{title}</h3>" + (f'<p class="tile-sub">{sub}</p>' if sub else ""))


def plot(fig: go.Figure, key: str) -> None:
    """Render a Plotly figure with the project template and no mode bar."""
    st.plotly_chart(fig, theme=None, key=key, config=PLOT_CONFIG)


def animated_plot(fig: go.Figure) -> None:
    """Render a figure whose frame "full" should play once on load (in an iframe)."""
    height = int(fig.layout.height or 450)
    html = fig.to_html(include_plotlyjs="cdn", full_html=True, auto_play=False, config=PLOT_CONFIG,
                       post_script=ANIMATE_IN, default_height=f"{height}px")
    style = f"<style>@import url('{theme.FONT_URL}');body{{margin:0;background:transparent}}</style>"
    st.iframe(html.replace("<head>", f"<head>{style}", 1), height=height + 10)


@contextmanager
def loading(label: str) -> Iterator[None]:
    """Spinner around data loading; an OpenF1 failure becomes a friendly message, not a traceback."""
    try:
        with st.spinner(label):
            yield
    except OpenF1Error as exc:
        state.stop_with_error(
            "OpenF1 did not answer, so this view cannot be loaded right now. Try again in a minute, or "
            f"switch to the 2024 Hungarian Grand Prix, which works offline.\n\nDetails: {exc}"
        )


def table(df, index: bool = False, scroll: bool = False) -> None:
    """A plain HTML table that follows the page styling (st.dataframe is always light)."""
    html = df.to_html(index=index, classes="ri-table", border=0, na_rep="–", justify="unset")
    st.html(f'<div class="ri-table-wrap{" scroll" if scroll else ""}">{html}</div>')


def _hero(section: str):
    """Open the hero of a section: page CSS, the header container and its backdrop canvas."""
    st.session_state.section = section  # HTML components read this to pick the matching dark tokens
    inject_css(extra=theme.section_css(section))
    hero = st.container(key=f"hero-{section}")
    hero.html('<div class="hero-art"><canvas id="hero-art" aria-hidden="true"></canvas></div>')
    return hero


def _hero_animation(scene: dict | None) -> None:
    """Start the hero backdrop (decoration only, drawn from the selected session's data)."""
    if scene:
        st.html(f"<script>{render_template('decor.js', scene)}</script>", unsafe_allow_javascript=True)


def _scene(section: str, selection: state.Selection) -> dict | None:
    """Backdrop data: lap-time flow lines for Analytics, the circuit outline for Races."""
    if section == "analytics":
        return decor.flow_scene(selection.session_key, selection.session_name in RACE_SESSIONS)
    return decor.circuit_scene(selection.session_key)


def hero_title(section: str, title: str, meta: str) -> None:
    """A hero with a plain title, for pages that do not depend on the race selection."""
    hero = _hero(section)
    selection = state.resolve()
    with hero:
        st.html(f'<span class="accent-bar"></span><p class="gp-title">{title}</p><p class="gp-meta">{meta}</p>')
    _hero_animation(_scene(section, selection))


def page_header(section: str = "analytics") -> state.Selection:
    """Shared header of the inner pages: weekend, session, selector, back to start, over the backdrop."""
    hero = _hero(section)
    selection = state.resolve()
    meeting = selection.meeting
    session_date = selection.sessions.loc[selection.session_name, "date_start"]
    badge = '<span class="badge">Offline demo data</span>' if selection.is_demo else ""
    with hero:
        left, right = st.columns([5, 2], vertical_alignment="bottom")
        left.html(
            f'<span class="accent-bar"></span><p class="gp-title">{meeting["meeting_name"]}</p>'
            f'<p class="gp-meta"><strong>{selection.session_name}</strong>, '
            f'{session_date.day} {session_date:%B %Y}, '
            f'{meeting["circuit_short_name"]}, {meeting["country_name"]}{badge}</p>'
        )
        with right.container(horizontal=True, horizontal_alignment="right"):
            st.page_link("views/landing.py", label="Start", icon=":material/arrow_back:")
            with st.popover("Change race", icon=":material/tune:"):
                state.selector(selection)
    _hero_animation(_scene(section, selection))
    return selection


def is_race(selection: state.Selection) -> bool:
    """True for sessions with wheel-to-wheel racing (Race, Sprint)."""
    return selection.session_name in RACE_SESSIONS


def empty_state(message: str, title: str = "Nothing to show yet") -> None:
    """A calm message for "nothing to show", then stop the page."""
    with tile("empty", "gray"):
        st.html(f'<h3>{title}</h3><p class="tile-sub">{message}</p>')
    footer()
    st.stop()


def footer() -> None:
    st.html(
        f'<p class="app-footer">{DISCLAIMER} Built by Dominik Nagy. '
        f'<a href="{REPO_URL}" target="_blank" rel="noopener">Source on GitHub</a></p>'
    )
