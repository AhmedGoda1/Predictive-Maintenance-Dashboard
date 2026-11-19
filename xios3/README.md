# XIOS3 technician app

A maintenance technician app for this pipeline, built with XIOS3 on CloudBackend. It uses only built-in XIOS3
components (grids, labels, chart, form fields, buttons) and XML processes, with no custom JavaScript, and keeps its
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
| `index.html` | Boot page for the deployed site. Pressing ▶ in VS Code rewrites it for local use, so upload this version. |
| `data/fleet.xml`, `data/alerts.xml`, `data/history/*.xml` | Pipeline results, written by `python scripts/export_xios3.py` |
| `data/workorders.xml` | Empty starting document. The first time a user opens the app, it copies it to their `home://workorders.xml` and saves work orders there. Files uploaded with the app (`host://`) are read-only once deployed, and `home://` only exists for a signed-in user, which is why the manifest starts the platform's login application (`xios://apps/login.xml`) first. |

## Refresh the data

```bash
python scripts/export_xios3.py      # from the repository root; builds maintenance.db first if it is missing
```

Then upload the `data` folder again (see below). Work orders are not touched, since they live in the user's Documents.

## Upload and deploy with the CloudBackend VS Code extension

1. Open this `xios3` folder in VS Code and run `CloudBackend: Sign in`.
2. In the CloudBackend sidebar's Projects view, create a project folder (for example `PdmTechnician`).
3. Run `CloudBackend: Upload all project files to…` and pick that folder.
4. In CloudBackend PaaS, open the Projects tab, select the project and deploy it.

## Unverified parts

The XIOS3 runtime could not be run outside CloudBackend while this was written, so the manifest was checked
against the extension's schemas (2.4.0) only. These parts follow the schema docs but are the most likely to need
adjustment on the first deployment:

- the data format of the health chart (`<serie>` / `<axis>` at the top of each history file);
- `host://data/...` as the path to files uploaded with the app;
- aliases set in one step (`$fleet`, `$alerts`, `$orders`, `$alert`) being visible in later steps;
- the first-run copy of `workorders.xml` into `home://`.
