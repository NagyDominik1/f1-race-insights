# F1 Race Insights

Streamlit app for analysing Formula 1 sessions (seasons 2023-2026). Work in progress:
currently shows lap times per driver for a selected race, qualifying or sprint.

Data source: [OpenF1](https://openf1.org) – an unofficial API, not affiliated with
Formula 1. No account or API key needed; the 2024 Hungarian Grand Prix is bundled
as offline demo data in `data/demo/`.

Run locally: `pip install -r requirements.txt` then `streamlit run app.py`.
Tests: `pip install -r requirements-dev.txt` then `pytest`.
