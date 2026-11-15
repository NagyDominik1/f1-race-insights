"""Landing page: a split screen with two tiles, Analytics and Races."""

import streamlit as st

from ui import components, decor, state

def tile_html(canvas_id: str, title: str, text: str, cta: str) -> str:
    return (
        f'<div class="lt-tile"><canvas id="{canvas_id}" aria-hidden="true"></canvas>'
        f'<div class="lt-copy"><h2>{title}</h2><p>{text}</p><span class="lt-cta">{cta}</span></div></div>'
    )


# the intro plays once per Streamlit session; ?intro=0 skips it (the browser also remembers it per tab)
show_intro = not st.session_state.get("intro_shown") and st.query_params.get("intro") != "0"
st.session_state.intro_shown = True
state.resolve()  # keeps the selection in the URL, so a shared link opens the same race
components.inject_css(extra=components.template_text("landing.css") + components.template_text("intro.css"))
if show_intro:
    st.html(decor.intro_html())
    st.html(f"<script>{decor.logo_script()}{components.template_text('intro.js')}</script>", unsafe_allow_javascript=True)

with st.container(key="landing"):
    st.html(
        f'<div class="lt-brand"><i data-logo="ink"></i><span>{decor.TAGLINE}</span></div>'
    )
    analytics, races = st.columns(2)
    with analytics.container(key="lt-analytics"):
        st.html(tile_html(
            "lt-lines", "Analytics",
            "Pace, tyre strategy and head-to-head statistics, with the method behind every number.",
            "Open analytics",
        ))
        if st.button("Open analytics", key="go_analytics"):
            st.switch_page("views/overview.py")
    with races.container(key="lt-races"):
        st.html(tile_html(
            "lt-track", "Races",
            "Replay a Grand Prix on the track map, or set two fastest laps against each other.",
            "Watch the replay",
        ))
        if st.button("Watch the replay", key="go_races"):
            st.switch_page("views/replay.py")
    st.html(
        f'<div class="lt-foot"><span>Built by Dominik Nagy. <a href="{components.REPO_URL}" '
        f'target="_blank" rel="noopener">Source on GitHub</a></span><span>{components.DISCLAIMER}</span></div>'
    )

payload = decor.demo_scene()
script = components.render_template("landing.js", payload) if payload else ""
st.html(f"<script>{decor.logo_script()}{script}</script>", unsafe_allow_javascript=True)
