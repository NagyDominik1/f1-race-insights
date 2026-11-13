"""Reusable UI pieces: global CSS, bento tiles, the page header and HTML components."""

import json
from functools import lru_cache
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from f1insights import theme
from ui import state

TEMPLATE_DIR = Path(__file__).parent / "templates"
REPO_URL = "https://github.com/NagyDominik1/f1-race-insights"
DISCLAIMER = "Unofficial project. Data from OpenF1. Not affiliated with Formula 1."


def inject_css() -> None:
    """The single global style block, plus the shared Plotly template."""
    theme.register_plotly_template()
    st.html(f"<style>{theme.global_css()}</style>")


@lru_cache
def _template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def render_template(name: str, payload: dict) -> str:
    """Fill an HTML template with the design tokens, the shared car drawing and JSON data."""
    blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    head = f"@import url('{theme.FONT_URL}');{theme.css_variables()}"
    html = _template(name).replace("/*__TOKENS__*/", head).replace("/*__CAR__*/", _template("car.js"))
    return html.replace("__DATA__", blob)


def embed(name: str, payload: dict, height: int) -> None:
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
    st.plotly_chart(fig, theme=None, key=key, config={"displayModeBar": False})


def page_header() -> state.Selection:
    """Shared header of the inner pages: weekend, session, selector, back to start."""
    selection = state.resolve()
    meeting = selection.meeting
    session_date = selection.sessions.loc[selection.session_name, "date_start"]
    badge = '<span class="badge">Offline demo data</span>' if selection.is_demo else ""
    left, right = st.columns([5, 2], vertical_alignment="bottom")
    left.html(
        f'<p class="gp-title">{meeting["meeting_name"]}</p>'
        f'<p class="gp-meta"><strong>{selection.session_name}</strong>, '
        f'{session_date.day} {session_date:%B %Y}, '
        f'{meeting["circuit_short_name"]}, {meeting["country_name"]}{badge}</p>'
    )
    with right.container(horizontal=True, horizontal_alignment="right"):
        st.page_link("views/landing.py", label="Start", icon=":material/arrow_back:")
        with st.popover("Change race", icon=":material/tune:"):
            state.selector(selection)
    return selection


def empty_state(message: str) -> None:
    """A calm message for "nothing to show", then stop the page."""
    with tile("empty", "gray"):
        st.html(f'<h3>Nothing to show yet</h3><p class="tile-sub">{message}</p>')
    footer()
    st.stop()


def footer() -> None:
    st.html(
        f'<p class="app-footer">{DISCLAIMER} Built by Dominik Nagy. '
        f'<a href="{REPO_URL}" target="_blank" rel="noopener">Source on GitHub</a></p>'
    )
