# Sending work orders to a maintenance system: step by step

> **Optional.** Without any of this, work orders already reach the maintenance team: they appear on the
> maintenance login's page, where technicians start, complete or reject them (see [LOGIN.md](LOGIN.md)). Use this
> guide only to also send them to an external system.

**Dispatch Work Order** on an alert sends a work order to another service: your maintenance system (CMMS),
a ticketing tool, or an automation tool such as Power Automate, Zapier or n8n. That service then confirms the
order, and the dashboard shows what it said: *accepted*, *in progress*, *completed*, *rejected* or *cancelled*.

This guide assumes the maintenance side runs in **Node-RED** on your own computer, next to the dashboard. Node-RED
is free, runs locally and is wired up in a browser, so it can stand in for a CMMS today and later forward the work
orders to the real one. Part A sets up the whole round trip. Part B explains the formats, for when you build your
own flow or connect a real system. Part C covers the hosted dashboard.

Part A was run as written on Linux, with Node-RED 4.

---

## Part A: Node-RED on your own computer

```
dashboard ──POST /work-orders──▶ Node-RED (port 1880)
dashboard ◀──{"id": "CMMS-1", "status": "accepted"}──
dashboard ◀──MQTT pdm/v1/work_orders/<id>/status── Node-RED, when you click "Start work" or "Complete"
                    (through the Mosquitto broker on port 1883)
```

### 1. Install

```bash
pip install -r requirements.txt
npm install -g --unsafe-perm node-red            # needs Node.js 18 or newer (nodejs.org)
sudo apt install mosquitto mosquitto-clients     # Linux. macOS: brew install mosquitto. Windows: mosquitto.org/download
```

### 2. Start the broker (terminal 1)

```bash
mosquitto -c examples/mosquitto.conf
```

It listens on port 1883 of this computer only, with no password. Node-RED sends its status updates through it.

### 3. Start Node-RED and import the flow (terminal 2)

```bash
node-red
```

1. Open http://localhost:1880.
2. Menu (☰, top right) → **Import** → **select a file to import** → choose `examples/node-red-work-orders.json` →
   **Import**.
3. Press **Deploy** (top right). Under the *Send over MQTT* node you should see **connected**.

The flow, on its own tab *PdM work orders*:

| Node | What it does |
|---|---|
| **POST /work-orders** | Receives the work order from the dashboard. |
| **Check token, accept order** | Refuses a request without the right token (`demo-token`, change it in the node). Gives each new order a number `CMMS-1`, `CMMS-2`, … (a resent order keeps its number) and answers `{"id": "CMMS-1", "status": "accepted"}`. |
| **Work order received** | Shows the order in the debug sidebar (🐞 icon, top right). |
| **Start work / Complete / Reject** | Buttons: click the square on the left of the node to report that status for the last order received. |
| **Status of the last order** | Builds the confirmation `{"status": ..., "external_id": "CMMS-1", "note": ...}`. |
| **Send over MQTT** | Publishes it to the topic the work order names in `reply_to.mqtt_topic`. |
| **Refused by the dashboard** | Shows any confirmation the dashboard refused, with the reason. |

### 4. Start the dashboard (terminal 3)

```bash
PDM_WORK_ORDER_URL=http://localhost:1880/work-orders \
PDM_WORK_ORDER_TOKEN=demo-token \
PDM_MQTT_HOST=localhost \
streamlit run dashboard/app.py
```

`PDM_MQTT_HOST` makes the dashboard listen to the broker, which is how Node-RED's updates reach it. (On Windows
PowerShell, set each variable first: `$env:PDM_WORK_ORDER_URL="http://localhost:1880/work-orders"`, and so on.)

### 5. Dispatch a work order

1. In the dashboard, open **Asset detail** and pick an asset with alerts (the DC motor `MTR_01` has several).
2. Open the **🚨 Alerts & Actions** tab and press **Dispatch Work Order** on an alert.
3. The alert shows *"Work order WO-MTR_01-5 sent to http://localhost:1880/work-orders (HTTP 201)"* and
   *"📥 Status: accepted as CMMS-1"*. In Node-RED, the debug sidebar shows the order.

### 6. Report back from Node-RED

1. In Node-RED, click the button of **Start work**. Back in the dashboard, click anywhere (or reload): the alert
   shows *"🔧 Status: in progress as CMMS-1: Technician on site"*.
2. Click **Complete**: *"✅ Status: completed as CMMS-1: Repaired and tested"*.

That is the whole round trip. To connect a real maintenance system later, keep the **POST /work-orders** node and
replace what comes after it: an **http request** node that creates the order in your CMMS's API, and a second
**http in** node (or an **mqtt in**, or a timer that polls the CMMS) that turns the CMMS's updates into the
confirmation message of Part B, step 4.

### Without MQTT: confirm over HTTP instead

If you don't want a broker, the dashboard can receive updates over HTTP:

1. In a fourth terminal: `PDM_WORK_ORDER_CALLBACK_TOKEN=demo-callback python -m pdm.work_order_callback`
   (port 8502; the token must match `CALLBACK_TOKEN` in the *Status of the last order* node).
2. In Node-RED, double-click **Send over MQTT** and disable it (toggle at the bottom of the dialog), enable
   **Or send over HTTP** and **Callback answer** the same way, then **Deploy**.
3. Start the dashboard with `PDM_WORK_ORDER_CALLBACK_URL=http://localhost:8502` instead of `PDM_MQTT_HOST`.

The buttons now POST to `http://localhost:8502/work-orders/<id>/status`; *Callback answer* shows `200` when the
dashboard stored the update.

### If you run Node-RED in Docker

Inside the container, `localhost` is the container itself. Use `host.docker.internal` (Docker Desktop) in the
*Local broker* settings and in the callback URL, and publish port 1880: `docker run -p 1880:1880 nodered/node-red`.

### No Node-RED?

`examples/work_order_receiver.py` does the same in Python:
`python examples/work_order_receiver.py --port 1880 --token demo-token --complete-after 20 --mqtt-host localhost`
accepts every order and reports it completed 20 seconds later.

---

## Part B: the formats, for your own flow or a real system

### 1. Point the dashboard at the service

| Variable | Required | What it is |
|---|---|---|
| `PDM_WORK_ORDER_URL` | yes | The URL the work order is POSTed to, `http://` or `https://`. Without it, orders stay in the dashboard, on the maintenance page. |
| `PDM_WORK_ORDER_TOKEN` | no | Sent as `Authorization: Bearer <token>`. Use it if your service expects a bearer token. |
| `PDM_WORK_ORDER_TIMEOUT` | no | Seconds to wait for the service (default 10). |

For services that want a different kind of authentication (an API key header, OAuth), put a small automation flow
(Power Automate, Zapier, n8n, Node-RED) in between: it takes the webhook and calls the real API.

### 2. Make the service accept the work order

The dashboard sends one HTTP POST per order with `Content-Type: application/json`:

```json
{
  "schema": "pdm.work_order.v1",
  "work_order_id": "WO-MTR_01-5",
  "created_at": "2026-10-19 10:23:36",
  "priority": "urgent",
  "requested_by": null,
  "asset": {"asset_id": "MTR_01", "name": "Brushed DC Motor (run-to-failure test)", "type": "brushed_dc_motor",
            "type_name": "Brushed DC motor", "site": "..."},
  "alert": {"alert_id": 5, "raised_at": "...", "level": "Failed",
            "detected_issue": "Brushed DC motor stopped working", "suggested_action": "..."},
  "condition": {"status": "Failed", "health_score": 3.1, "top_driver": "...", "age": 5400.0,
                "rul_estimate": 0.0, "rul_low": 0.0, "rul_high": 0.0, "unit": "s"},
  "reply_to": {"statuses": ["accepted", "in_progress", "completed", "rejected", "cancelled"],
               "mqtt_topic": "pdm/v1/work_orders/WO-MTR_01-5/status",
               "http_url": "https://pdm.example.com/work-orders/WO-MTR_01-5/status"}
}
```

- `priority` is `urgent` for a Failed asset, `high` for Critical, `medium` for Warning. Map it onto your
  system's priorities.
- `condition` is the asset's state when the alert was raised. `unit` is the unit of `age` and the RUL numbers.
- `reply_to` tells the service where to send updates (step 4). A field is `null` when that route isn't set up.
- The `Idempotency-Key` header carries the `work_order_id`. If someone presses **Send again** after a failure, the
  same id arrives a second time. Your service should then return the existing order instead of creating a new one.

Your service must answer with a **2xx status** (200, 201, 202). Any other answer, or no answer within the timeout,
counts as a failed delivery: the dashboard shows the error and offers **Send Work Order again**.

### 3. Confirm right away in the answer (simplest)

If your service answers the POST with a JSON body like this, the dashboard records the first confirmation at once:

```json
{"id": "CMMS-1234", "status": "accepted"}
```

`id` (or `external_id`) is your system's own order number; the dashboard shows it next to the status. Without
a `status` in the answer, the order shows as *sent, waiting for the service to confirm*.

### 4. Send later updates

When the order changes in your system (a technician starts it, closes it, or it's rejected), send a confirmation
message:

```json
{"status": "completed", "external_id": "CMMS-1234", "note": "Bearing replaced", "at": "2026-10-19T14:05:00Z"}
```

| Field | Required | Meaning |
|---|---|---|
| `status` | yes | `accepted`, `in_progress`, `completed`, `rejected` or `cancelled` |
| `external_id` | no | Your order number (kept from earlier messages if you leave it out) |
| `note` | no | Free text shown on the alert, at most 500 characters |
| `at` | no | When it happened (ISO 8601; default: when it arrives). A message older than the last one stored is ignored, so updates arriving out of order can't move an order backwards. |

There are two ways to send it. Pick the one your service can do.

### 5. Option 1: HTTP (when you run the dashboard on your own server)

1. Pick a long random secret, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Run the endpoint next to the dashboard (same machine, same database):

   ```bash
   PDM_WORK_ORDER_CALLBACK_TOKEN=<secret> python -m pdm.work_order_callback
   ```

   It listens on `0.0.0.0:8502`; change that with `PDM_WORK_ORDER_CALLBACK_HOST` / `_PORT`.
3. Make it reachable for your service. Over the internet, put it behind HTTPS (a reverse proxy such as nginx or
   Caddy), because the secret travels in every request.
4. Tell the dashboard its public address, so work orders carry it in `reply_to.http_url`:
   `PDM_WORK_ORDER_CALLBACK_URL=https://pdm.example.com`.
5. In your service, send each update as

   ```bash
   curl -X POST https://pdm.example.com/work-orders/WO-MTR_01-5/status \
        -H "Authorization: Bearer <secret>" -H "Content-Type: application/json" \
        -d '{"status": "in_progress", "note": "Technician on site"}'
   ```

   Answers: `200` stored, `400` malformed message (the body says why), `401` wrong or missing secret,
   `404` unknown work order.

### 6. Option 2: MQTT (also works on the hosted dashboard)

If the dashboard already uses an MQTT broker for live data, the ingestion service listens for confirmations too.

1. Give the maintenance service its own broker user that may only write confirmations. With Mosquitto, add to the
   ACL file:

   ```
   user maintenance-service
   topic write pdm/v1/work_orders/+/status
   topic read  pdm/v1/work_orders/+/rejected
   ```

   The ingestion service's user needs `topic read pdm/v1/work_orders/+/status` and
   `topic write pdm/v1/work_orders/+/rejected`.
2. Your service publishes each update with QoS 1 to `pdm/v1/work_orders/<work_order_id>/status`
   (the work order's `reply_to.mqtt_topic`):

   ```bash
   mosquitto_pub -h broker.example.com -p 8883 -u maintenance-service -P '...' -q 1 \
       -t pdm/v1/work_orders/WO-MTR_01-5/status -m '{"status": "completed", "note": "Bearing replaced"}'
   ```

3. A message that is refused (bad JSON, an unknown status, an unknown work order) is answered on
   `pdm/v1/work_orders/<work_order_id>/rejected` with the reason. Subscribe to it while you set things up:
   `mosquitto_sub -t 'pdm/v1/work_orders/+/rejected' -v`.

---

## Part C: on the hosted dashboard (Streamlit Cloud)

1. In Streamlit's *Manage app* menu, open *Settings → Secrets* and add

   ```toml
   PDM_WORK_ORDER_URL = "https://your-service.example.com/work-orders"
   PDM_WORK_ORDER_TOKEN = "..."            # only if your service wants one
   ```

2. For updates after the first answer, use **MQTT** (Part B, step 6): the hosted app runs the ingestion service
   itself when `PDM_MQTT_HOST` and the other broker secrets are set (see [LIVE_DATA.md](LIVE_DATA.md), Part B).
   Streamlit Cloud can only run the dashboard, so the HTTP endpoint of option 1 is not available there.
3. The service must be reachable from the internet: Streamlit Cloud can't reach `localhost` or your company
   network. A Node-RED on your laptop is therefore out of reach for the hosted app; run it on a server, or expose
   it with a tunnel (ngrok, Cloudflare Tunnel) for a test, and point the flow's *Local broker* at the same broker
   the hosted app uses.

**Not tested here:** a hosted Streamlit app with these secrets and a real CMMS. Part A was run end to end with
Node-RED, over both MQTT and HTTP. As with the live data, the hosted app keeps its database on temporary disk, so
work orders are lost when the app restarts.

---

## When something does not work

| You see | Likely cause |
|---|---|
| *"created. It is on the maintenance team's list"*, but nothing reaches your service | `PDM_WORK_ORDER_URL` is not set (or not in the app's secrets). Restart the app after setting it. |
| *"could not be delivered … (HTTP 401 …)"* | The service wants a different token: check `PDM_WORK_ORDER_TOKEN`. |
| *"could not be delivered … (Connection refused)"* or *"timed out"* | The URL is wrong, the service is down, or it isn't reachable from where the dashboard runs. |
| *"sent … Waiting for the service to confirm"* stays | The service answered 2xx without a `status`, and no update arrived. Check the update route (step 5 or 6). |
| `401` from the callback endpoint | The service's bearer secret doesn't match `PDM_WORK_ORDER_CALLBACK_TOKEN`. |
| `404` from the callback, or `not_found` on the `rejected` topic | The work order id is misspelled, or the dashboard's database was rebuilt since the order was sent. |
| Node-RED's *Send over MQTT* says *disconnected* | The broker is not running, or the *Local broker* settings point elsewhere. |
| Node-RED answers 401 | `PDM_WORK_ORDER_TOKEN` differs from `TOKEN` in *Check token, accept order*. |
| Node-RED warns *No work order received yet* | Node-RED was restarted (it forgets orders) or nothing was dispatched: dispatch again. |
| A status doesn't change | The update's `at` is older than the status already stored, so it was ignored. |
