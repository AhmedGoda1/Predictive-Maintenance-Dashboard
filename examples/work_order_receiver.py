"""A stand-in for a maintenance system (CMMS): receives work orders from the dashboard and confirms them.

It accepts every work order, answers {"id": "DEMO-<n>", "status": "accepted"} (the dashboard reads that as the
first confirmation) and, with --complete-after, reports the order completed a few seconds later the way a
real system would when the technician closes it: over MQTT (--mqtt-host) or over the HTTP callback named in
the work order's reply_to (--callback-token). Nothing but the standard library (and paho-mqtt for MQTT).

  python examples/work_order_receiver.py --port 8600
  # then: PDM_WORK_ORDER_URL=http://localhost:8600/work-orders streamlit run dashboard/app.py
"""
import argparse
import itertools
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

counter = itertools.count(1)
seen = {}                                      # work order id -> our id (the Idempotency-Key makes resends safe)


def report(order: dict, status: str, external_id: str, args) -> None:
    """Tells the dashboard what became of the order, over MQTT or HTTP."""
    message = {"status": status, "external_id": external_id, "note": "closed by the demo receiver"}
    if args.mqtt_host:
        import paho.mqtt.publish as publish
        auth = {"username": args.mqtt_username, "password": args.mqtt_password} if args.mqtt_username else None
        publish.single(order["reply_to"]["mqtt_topic"] or f"pdm/v1/work_orders/{order['work_order_id']}/status",
                       json.dumps(message), qos=1, hostname=args.mqtt_host, port=args.mqtt_port, auth=auth,
                       tls={} if args.mqtt_tls else None)
    elif args.callback_token and order["reply_to"]["http_url"]:
        request = urllib.request.Request(order["reply_to"]["http_url"], data=json.dumps(message).encode(),
                                         method="POST", headers={"Content-Type": "application/json",
                                                                 "Authorization": f"Bearer {args.callback_token}"})
        with urllib.request.urlopen(request, timeout=10) as response:
            print("  callback answered", response.status)
    else:
        print("  no way to report back: give --mqtt-host, or --callback-token with PDM_WORK_ORDER_CALLBACK_URL set")
        return
    print(f"  reported {order['work_order_id']} as {status}")


def make_handler(args):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if args.token and self.headers.get("Authorization") != f"Bearer {args.token}":
                self.send_response(401)
                self.end_headers()
                return
            order = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            key = self.headers.get("Idempotency-Key") or order["work_order_id"]
            new = key not in seen
            external_id = seen.setdefault(key, f"DEMO-{next(counter)}")
            print(f"{'new' if new else 'repeated'} work order {order['work_order_id']} -> {external_id}: "
                  f"{order['priority']} priority, {order['asset']['name']}: {order['alert']['detected_issue']}")
            body = json.dumps({"id": external_id, "status": "accepted"}).encode()
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            if new and args.complete_after is not None:
                threading.Timer(args.complete_after, report, (order, "completed", external_id, args)).start()

        def log_message(self, *a):
            pass

    return Handler


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8600)
    ap.add_argument("--token", help="require this bearer token (PDM_WORK_ORDER_TOKEN on the dashboard side)")
    ap.add_argument("--complete-after", type=float, help="report each order completed after this many seconds")
    ap.add_argument("--callback-token", help="PDM_WORK_ORDER_CALLBACK_TOKEN of pdm.work_order_callback")
    ap.add_argument("--mqtt-host")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--mqtt-username")
    ap.add_argument("--mqtt-password")
    ap.add_argument("--mqtt-tls", action="store_true")
    args = ap.parse_args()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(args))
    print(f"waiting for work orders on http://localhost:{args.port}/work-orders")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
