"""Demo app for Self-Healing Green Infra.
One codebase, deployed 3 ways: healthy, over-provisioned, crash-looping."""
import os, sys, time
from flask import Flask, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

APP_NAME = os.getenv("APP_NAME", "demo-app")

# Crash-loop scenario: if the app is told it needs a DB but DB_URL is missing, exit.
if os.getenv("REQUIRE_DB", "false").lower() == "true" and not os.getenv("DB_URL"):
    print(f"[{APP_NAME}] FATAL: DB_URL not set. Cannot connect to database. Exiting.", flush=True)
    sys.exit(1)

app = Flask(__name__)
REQUESTS = Counter("app_requests_total", "Total HTTP requests", ["app", "status"])
LATENCY = Histogram("app_request_seconds", "Request latency in seconds", ["app"])

@app.route("/")
def index():
    start = time.time()
    REQUESTS.labels(APP_NAME, "200").inc()
    LATENCY.labels(APP_NAME).observe(time.time() - start)
    return {"app": APP_NAME, "status": "ok", "db": "connected" if os.getenv("DB_URL") else "none"}

@app.route("/health")
def health():
    return {"status": "healthy"}

@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    print(f"[{APP_NAME}] starting on :8080", flush=True)
    app.run(host="0.0.0.0", port=8080)
