"""Streamlit entry point: page config, global styling and navigation."""

import streamlit as st

st.set_page_config(page_title="F1 Race Insights", page_icon="🏁", layout="wide")

pages = {
    "": [st.Page("views/landing.py", title="Start", url_path="start", default=True)],
    "Analytics": [
        st.Page("views/overview.py", title="Overview", url_path="overview"),
        st.Page("views/pace.py", title="Pace", url_path="pace"),
        st.Page("views/strategy.py", title="Strategy", url_path="strategy"),
        st.Page("views/head_to_head.py", title="Head-to-head", url_path="head-to-head"),
        st.Page("views/methodology.py", title="Methodology", url_path="methodology"),
    ],
    "Races": [
        st.Page("views/replay.py", title="Race replay", url_path="replay"),
        st.Page("views/ghost.py", title="Ghost lap", url_path="ghost-lap"),
    ],
}
st.navigation(pages, position="top").run()
