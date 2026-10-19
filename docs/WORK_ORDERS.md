# Sending work orders to a maintenance system: step by step

**Dispatch Work Order** on an alert sends a work order to another service: your maintenance system (CMMS),
a ticketing tool, or an automation tool such as Power Automate, Zapier or n8n. That service then confirms the
order, and the dashboard shows what it said: *accepted*, *in progress*, *completed*, *rejected* or *cancelled*.

```
dashboard ──POST work order (JSON)──▶ your service
dashboard ◀──"accepted" (in the answer)── your service
dashboard ◀──"in_progress", "completed" … (MQTT or HTTP)── your service, later
```

Part A tries the whole round trip on your own computer with a stand-in service. Part B connects a real service.
Part C covers the hosted dashboard. Every command in Part A was run as written on Linux.

---

## Part A: try it on your own computer

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Start the stand-in maintenance service (terminal 1)

`examples/work_order_receiver.py` plays the part of a CMMS. It accepts every work order, answers with its own
order number, and with `--complete-after` it reports the order completed a few seconds later.

```bash
python examples/work_order_receiver.py --port 8600 --token demo-token --complete-after 20 --callback-token demo-callback
```

### 3. Start the confirmation endpoint (terminal 2)

The service needs somewhere to send its later updates. Here that's the small HTTP endpoint that ships with the
dashboard. It writes into the same database the dashboard reads.

```bash
PDM_WORK_ORDER_CALLBACK_TOKEN=demo-callback python -m pdm.work_order_callback
```

It listens on port 8502. If you'd rather use MQTT, skip this step and see step 6 in Part B.

### 4. Start the dashboard (terminal 3)

```bash
PDM_WORK_ORDER_URL=http://localhost:8600/work-orders \
PDM_WORK_ORDER_TOKEN=demo-token \
PDM_WORK_ORDER_CALLBACK_URL=http://localhost:8502 \
streamlit run dashboard/app.py
```

### 5. Dispatch a work order

1. Open **Asset detail** and pick an asset with alerts (the DC motor `MTR_01` has several).
2. Open the **🚨 Alerts & Actions** tab and press **Dispatch Work Order** on an alert.
3. You'll see *"Work order WO-MTR_01-5 sent to http://localhost:8600/work-orders (HTTP 201)"*, and below it
   *"📥 Service reports accepted as DEMO-1"*. Terminal 1 prints the order it received.
4. After 20 seconds, the stand-in reports the order completed. Click anywhere in the dashboard (or reload) and the
   alert shows *"✅ Service reports completed as DEMO-1: closed by the demo receiver"*.

---

## Part B: connect your real service

### 1. Point the dashboard at the service

| Variable | Required | What it is |
|---|---|---|
| `PDM_WORK_ORDER_URL` | yes | The URL the work order is POSTed to, `http://` or `https://`. Without it, orders are only stored. |
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

To try MQTT with the stand-in: `python examples/work_order_receiver.py --complete-after 20 --mqtt-host localhost`
(with the broker and `python -m pdm.mqtt_ingest` running as in [LIVE_DATA.md](LIVE_DATA.md), Part A).

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
   network.

**Not tested here:** a hosted Streamlit app with these secrets and a real CMMS. Part A was run end to end, over
both HTTP and MQTT. As with the live data, the hosted app keeps its database on temporary disk, so work orders are
lost when the app restarts.

---

## When something does not work

| You see | Likely cause |
|---|---|
| *"stored, but not sent: no maintenance service is configured"* | `PDM_WORK_ORDER_URL` is not set (or not in the app's secrets). Restart the app after setting it. |
| *"could not be delivered … (HTTP 401 …)"* | The service wants a different token: check `PDM_WORK_ORDER_TOKEN`. |
| *"could not be delivered … (Connection refused)"* or *"timed out"* | The URL is wrong, the service is down, or it isn't reachable from where the dashboard runs. |
| *"sent … Waiting for the service to confirm"* stays | The service answered 2xx without a `status`, and no update arrived. Check the update route (step 5 or 6). |
| `401` from the callback endpoint | The service's bearer secret doesn't match `PDM_WORK_ORDER_CALLBACK_TOKEN`. |
| `404` from the callback, or `not_found` on the `rejected` topic | The work order id is misspelled, or the dashboard's database was rebuilt since the order was sent. |
| A status doesn't change | The update's `at` is older than the status already stored, so it was ignored. |
