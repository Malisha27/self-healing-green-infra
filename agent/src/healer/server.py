"""Agent 'doorbell': Alertmanager calls POST /alert -> the agent runs one heal cycle.
Only alerts labelled heal="true" trigger healing. Uses Python's built-in HTTP server (no extra deps)."""
import json, os, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from healer import main as agent

MODE = os.getenv("APPROVAL_MODE", "auto")
BRAIN = os.getenv("BRAIN", "llm")
PORT = int(os.getenv("PORT", "8085"))
_lock = threading.Lock()   # one heal at a time (Alertmanager may send the same alert repeatedly)

def heal_namespace(ns: str) -> None:
    if not _lock.acquire(blocking=False):
        agent.log("busy_skip", namespace=ns); return
    try:
        agent.run_once(ns, MODE, BRAIN)
    finally:
        _lock.release()

class Handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, body: str) -> None:
        self.send_response(code); self.end_headers(); self.wfile.write(body.encode())

    def do_GET(self):   # health check for Kubernetes probes
        self._reply(200, "ok") if self.path == "/healthz" else self._reply(404, "not found")

    def do_POST(self):
        if self.path != "/alert":
            return self._reply(404, "not found")
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        alerts = payload.get("alerts", [])
        targets = {a["labels"].get("namespace") for a in alerts
                   if a.get("status") == "firing" and a["labels"].get("heal") == "true"}
        targets.discard(None)
        agent.log("alert_received", alerts=[a["labels"].get("alertname") for a in alerts],
                  heal_namespaces=sorted(targets))
        for ns in targets:   # heal in the background so Alertmanager gets a fast reply
            threading.Thread(target=heal_namespace, args=(ns,), daemon=True).start()
        self._reply(202, "accepted")

    def log_message(self, *args):   # silence default access logs (we have JSON logs)
        pass

if __name__ == "__main__":
    agent.log("server_started", port=PORT, mode=MODE, brain=BRAIN)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
