"""HTTP endpoint where a maintenance service confirms work orders (the alternative to MQTT).

    POST /work-orders/<work_order_id>/status
    Authorization: Bearer <PDM_WORK_ORDER_CALLBACK_TOKEN>
    {"status": "accepted", "external_id": "CMMS-1234", "note": "...", "at": "2026-10-19T10:30:00Z"}

Answers 200 with the stored work order, 400 for a malformed message, 401 without the right token, 404 for an
unknown work order. It writes to the same database as the dashboard, so it must run on the same machine.
Streamlit Cloud cannot run it: there, the service confirms over MQTT instead (see pdm.work_orders).

Configuration (environment variables):
    PDM_WORK_ORDER_CALLBACK_TOKEN   required: the shared secret the service sends
    PDM_WORK_ORDER_CALLBACK_HOST    address to listen on (default 0.0.0.0)
    PDM_WORK_ORDER_CALLBACK_PORT    port (default 8502)

Run:  PDM_WORK_ORDER_CALLBACK_TOKEN=... python -m pdm.work_order_callback
Put it behind HTTPS (a reverse proxy) when the service reaches it over the internet: the token travels in
every request.
"""
import hmac
import json
import logging
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import work_orders

log = logging.getLogger("pdm.work_order_callback")

PATH = re.compile(r"^/work-orders/([A-Za-z0-9._-]{1,100})/status/?$")
MAX_BODY = 10_000


def make_server(token: str, host: str = "0.0.0.0", port: int = 8502, db_path=None) -> ThreadingHTTPServer:
    if not token:
        raise ValueError("a callback token is required")
    expected = f"Bearer {token}".encode()

    class Handler(BaseHTTPRequestHandler):
        def _answer(self, code: int, body: dict) -> None:
            data = json.dumps(body, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if not hmac.compare_digest(self.headers.get("Authorization", "").encode(), expected):
                return self._answer(401, {"error": "missing or wrong bearer token"})
            match = PATH.match(self.path)
            if match is None:
                return self._answer(404, {"error": "use POST /work-orders/<work_order_id>/status"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_BODY:
                return self._answer(413, {"error": f"send a body of at most {MAX_BODY} bytes with its Content-Length"})
            try:
                order = work_orders.confirm(match.group(1), json.loads(self.rfile.read(length)), db_path)
            except KeyError:
                return self._answer(404, {"error": f"no work order {match.group(1)}"})
            except ValueError as e:
                message = "body is not valid JSON" if isinstance(e, json.JSONDecodeError) else str(e)
                return self._answer(400, {"error": message})
            except Exception:
                log.exception("failed to store the status of %s", match.group(1))
                return self._answer(500, {"error": "internal error"})
            return self._answer(200, {k: order[k] for k in ("work_order_id", "status", "external_id", "status_at")})

        def log_message(self, fmt, *args):
            log.info("%s %s", self.address_string(), fmt % args)

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    token = os.environ.get("PDM_WORK_ORDER_CALLBACK_TOKEN")
    if not token:
        raise SystemExit("Set PDM_WORK_ORDER_CALLBACK_TOKEN to the secret the maintenance service will send.")
    host = os.environ.get("PDM_WORK_ORDER_CALLBACK_HOST", "0.0.0.0")
    port = int(os.environ.get("PDM_WORK_ORDER_CALLBACK_PORT", 8502))
    server = make_server(token, host, port)
    log.info("listening on http://%s:%s/work-orders/<id>/status", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
