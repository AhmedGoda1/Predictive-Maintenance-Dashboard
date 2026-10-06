# Dashboard

Link: https://predictive-maintenance-dashboard-3ldxwrb9s9av4egmvykm9k.streamlit.app

Streamlit app. It currently shows the brushed DC motor (one run to failure, replayed as a live stream). It reads
`maintenance.db` from the repository root and builds it from the committed datasets on first start if it is
missing. See the root `README.md` for the architecture, the RUL model and its results.

Run locally from the repository root: `streamlit run dashboard/app.py`

- `app.py`: layout and replay controls
- `data_source.py`: database access for the app (uses the `pdm` package)
- `components.py`, `utils.py`: KPI header and charts
