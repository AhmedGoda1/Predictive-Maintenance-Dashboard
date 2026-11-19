# XIOS3 technician app

A maintenance technician app for this pipeline, built with XIOS3 on CloudBackend. It uses only built-in XIOS3
components (grids, labels, a rendered SVG chart, form fields, buttons) and XML processes, with no custom JavaScript except the design kit's small Screen component, and keeps its
data in CloudBackend.

| Tab | What it does |
|---|---|
| **Fleet** | Every asset in maintenance-priority order (same order as the Streamlit fleet overview). Selecting one shows its status, health index, estimated remaining life with its interval, main driver, latest alert, a health chart and its alerts. |
| **Alerts** | Every alert, newest first. Selecting one fills a dispatch form (technician, due date, instructions). *Dispatch work order* creates one work order per alert. |
| **Work orders** | The technician's list. *Start*, *Complete* and *Reject* update the selected order's status. |

## Files

| Path | Purpose |
|---|---|
| `index.xml` | Application manifest: the view and the process (triggers and steps). CloudBackend deployments expect this name. |
| `index.html` | Boot page for the deployed site. Pressing Run (the play button) in VS Code rewrites it for local use, so upload this version. |
| `data/fleet.xml`, `data/alerts.xml`, `data/history/*.xml` | Pipeline results, written by `python scripts/export_xios3.py` |
| `styles/app.css`, `ui/DesignKit/` | Narrow-screen support: the Screen component from the CloudBackend plugin's design kit tells the process whether it runs on a phone, and `app.css` lets one card fill the width there. On a phone each tab shows its list first and the detail after a tap, with a Back button, and the grids show fewer columns. |
| `data/healthchart.xsl` | Draws the health chart as SVG (XIOS/3 has no chart component). |
| `data/workorders.xml` | Empty starting document. The first time a user opens the app, it copies it to their `home://workorders.xml` and saves work orders there. Files uploaded with the app (`host://`) are read-only once deployed, and `home://` only exists for a signed-in user, which is why the manifest starts the platform's login application (`xios://apps/login.xml`) first. |

## Refresh the data

```bash
python scripts/export_xios3.py      # from the repository root; builds maintenance.db first if it is missing
```

Then upload the `data` folder again (see below). Work orders are not touched, since they live in each user's `home://workorders.xml`.

## Upload and deploy with the CloudBackend VS Code extension

1. Open this `xios3` folder in VS Code and run `CloudBackend: Sign in`.
2. In the CloudBackend sidebar's Projects view, create a project folder (for example `PdmTechnician`).
3. In that project folder, create the sub-folders `data`, `data/history`, `styles`, `ui` and `ui/DesignKit` first
   (each folder is a container of its own), then run `CloudBackend: Upload all project files to...` and pick it.
4. In CloudBackend PaaS, open the Projects tab, select the project and deploy it.

## Status (2026-11-19)

Verified on a CloudBackend deployment: sign-in through the platform login app, fleet grid, asset detail and health
chart, alerts, dispatching work orders, Start/Complete/Reject and deleting completed orders (saved in the user's
`home://workorders.xml`), and the phone layout in the browser and in the Android test app (`../mobile/`).

Known console messages that come from the platform, not this app: a 404 for `/v1/wsg3/<tenant>/:Tenant/` (the tenant
has no published `Tenant` container) and "No view to act on" from the login app's own `signin.xml`.

Not yet done: `<login session="true">` (keeps users signed in; the VS Code extension 2.4.0 schema rejects it, so it is
untested on CloudBackend), the design kit's token theme, and admin/technician roles.
