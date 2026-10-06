# Dashboard

Link: https://predictive-maintenance-dashboard-3ldxwrb9s9av4egmvykm9k.streamlit.app

Streamlit app with a fleet overview (all assets ranked by maintenance priority) and an asset detail view. The
recorded runs are replayed as if they were live. It reads
`maintenance.db` from the repository root and builds it from the committed datasets on first start if it is
missing. See the root `README.md` for the architecture, the RUL model and its results.

Run locally from the repository root: `streamlit run dashboard/app.py`

- `app.py`: navigation (Fleet / Asset detail)
- `fleet_view.py`, `asset_view.py`: the two views (asset detail has its own replay controls)
- `data_source.py`: database access for the app (uses the `pdm` package)
- `components.py`, `utils.py`: KPI rows and charts
