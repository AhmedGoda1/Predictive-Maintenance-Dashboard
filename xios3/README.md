# XIOS3 technician app

A maintenance technician app for this pipeline, built with XIOS3 on CloudBackend. It uses only built-in XIOS3
components (grids, labels, a rendered SVG chart, form fields, buttons) and XML processes, with no custom JavaScript except the design kit's small Screen component, and keeps its
data in CloudBackend.

| Tab | What it does |
|---|---|
| **Fleet** | Every asset in maintenance-priority order (same order as the Streamlit fleet overview). Selecting one shows its status, health index, estimated remaining life with its interval, main driver, latest alert, a health chart and its alerts. |
| **Alerts** | Every alert, newest first. Selecting one fills a dispatch form (technician, due date, instructions). *Dispatch work order* creates one work order per alert. |
| **Work orders** | The technician's list. *Start*, *Complete* and *Reject* update the selected order's status. |

Like the Streamlit dashboard, there are two kinds of login (see *Logins: admin and technician* below). An **admin**
sees all three tabs and can delete completed orders. A **technician** sees only the Work orders tab. Work orders
are shared, so an order an admin dispatches shows up on every technician's list.

## Files

| Path | Purpose |
|---|---|
| `index.xml` | Application manifest: the view and the process (triggers and steps). CloudBackend deployments expect this name. |
| `index.html` | Boot page for the deployed site. Pressing Run (the play button) in VS Code rewrites it for local use, so upload this version. |
| `data/fleet.xml`, `data/alerts.xml`, `data/history/*.xml` | Pipeline results, written by `python scripts/export_xios3.py` |
| `styles/app.css`, `ui/DesignKit/` | Narrow-screen support: the Screen component from the CloudBackend plugin's design kit tells the process whether it runs on a phone, and `app.css` lets one card fill the width there. On a phone each tab shows its list first and the detail after a tap, with a Back button, and the grids show fewer columns. |
| `data/healthchart.xsl` | Draws the health chart as SVG (XIOS/3 has no chart component). |
| `data/workorders.xml` | Empty starting document. The first time anyone opens the app, it copies it to the tenant's shared `tenant://PdM/workorders.xml` and saves every work order there. Files uploaded with the app (`host://`) are read-only once deployed. The manifest starts the platform's login application (`xios://apps/login.xml`) first, so the app always knows who is signed in. |
| `tenant-setup/admin.xml` | Role marker, not part of the app upload: goes in `tenant://PdM/Admins/` (see below). |

## Refresh the data

```bash
python scripts/export_xios3.py      # from the repository root; builds maintenance.db first if it is missing
```

Then upload the `data` folder again (see below). Work orders are not touched, since they live in `tenant://PdM/workorders.xml`.

## Upload and deploy with the CloudBackend VS Code extension

1. Open this `xios3` folder in VS Code and run `CloudBackend: Sign in`.
2. In the CloudBackend sidebar's Projects view, create a project folder (for example `PdmTechnician`).
3. In that project folder, create the sub-folders `data`, `data/history`, `styles`, `ui` and `ui/DesignKit` first
   (each folder is a container of its own), then run `CloudBackend: Upload all project files to...` and pick it.
4. In CloudBackend PaaS, open the Projects tab, select the project and deploy it.

## Logins: admin and technician

Everyone signs in with their own CloudBackend identity, a username and password separate from your owner login.
The app decides the role from an access rule: whoever can read `tenant://PdM/Admins/admin.xml` is an admin;
everyone else is a technician. CloudBackend gives an app no documented way to ask for the signed-in user's role,
so the access rule is the role. The tenant owner can read everything, so your own account is always an admin.

One-time setup in CloudBackend PaaS, signed in as the owner:

1. **Shared container.** In the Database Explorer, open `tenant://` and create a container named `PdM`. In its
   ACL, give the tenant group (all your users) **Read Write** (3), so technicians can update orders. Leave
   the Owner/Administrator entries with all permissions.
2. **Admins container.** Inside `PdM`, create a container named `Admins`. In its ACL, set the tenant group to
   **No Permission** (0), so it does not inherit the read access from `PdM`. Keep the Owner/Administrator entries.
3. Upload `tenant-setup/admin.xml` into `tenant://PdM/Admins/`.
4. **Accounts.** In **Identities › Create**, make one identity per person, with a username, email and first
   password. Leave the role empty: a role opens the CloudBackend console, which app users do not need.
5. **Admins.** For each identity that should be an admin, add a user entry with **Read** (1) to the ACL of
   the `tenant://PdM/Admins/` container **and** of `admin.xml`. The container entry matters: without it the
   app cannot look inside `Admins`, and the admin gets the technician view (found on the first deployment).
6. **Deployment.** A development deployment is private to your account. To let other identities sign in, make
   it public or promote it to Shared in **Projects**, and use that address (also in `../mobile/`'s
   `capacitor.config.json` `server.url`).

To test, sign in with each account in a **private browser window**: signing in from a normal tab replaces your
console session. An admin sees *Signed in as admin* and three tabs; a technician sees *Signed in as technician*
and only the Work orders tab.

Two things to know: two people saving at the same moment can overwrite each other's change, since all orders are
one document; and the role check hides the admin tabs, while the ACLs above are what actually protect the
data.

## What was done on 2026-11-19

- Checked against the CloudBackend docs, the plugin's linter and the extension's schemas: start-up on `Loaded`, the
  first-run copy of `workorders.xml` in an `otherwise` branch (the docs: `exists="false"` never runs), sign-up and
  reset links on the login, a Sign out button, ASCII-only files.
- Health chart: a `render` with `data/healthchart.xsl` draws the history as SVG (XIOS/3 has no chart component).
- Work-order grid: refreshed by `datachange` and `update` only; binding it again after every save broke row selection.
- Phone layout: `ui/DesignKit/` (the design kit's Screen component) tells the process when it runs on a phone;
  `styles/app.css` lets one card fill the width; each tab shows its list, then the detail with a Back button.
- `index.html` carries the plugin boot page's phone fixes, so the platform's login card fits a phone.
- *Delete completed orders* on the Work orders tab, with an in-app confirmation.
- Wrapped as an Android test app in `../mobile/`.
- Admin and technician logins: shared work orders in `tenant://PdM/`, and the role read from the `Admins`
  container's ACL. Verified on a Shared deployment on 2026-11-20 with an admin and a technician account.

## Status (2026-11-19)

Verified on a CloudBackend deployment: sign-in through the platform login app, fleet grid, asset detail and health
chart, alerts, dispatching work orders, Start/Complete/Reject and deleting completed orders (saved in the user's
`home://workorders.xml` at the time), and the phone layout in the browser and in the Android test app (`../mobile/`).

Known console messages that come from the platform, not this app: a 404 for `/v1/wsg3/<tenant>/:Tenant/` (the tenant
has no published `Tenant` container) and "No view to act on" from the login app's own `signin.xml`.

Not yet done: `<login session="true">` (keeps users signed in; the VS Code extension 2.4.0 schema rejects it, so it is
untested on CloudBackend), the design kit's token theme, and admin/technician roles.
