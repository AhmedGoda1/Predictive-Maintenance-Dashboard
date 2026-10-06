# Dashboard

Link: https://predictive-maintenance-dashboard-3ldxwrb9s9av4egmvykm9k.streamlit.app

Streamlit app for the brushed DC motor run-to-failure data. It reads `maintenance.db` from the repository
root (and builds it from `data/` on first start if it is missing). See the root `README.md` for the pipeline,
method and limitations.

Run locally from the repository root: `streamlit run dashboard/app.py`

- `app.py`: layout and replay controls
- `data_source.py`: database access for the app
- `components.py`, `utils.py`: KPI header and charts
