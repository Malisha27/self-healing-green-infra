"""Prometheus tool: lets the agent ask PromQL questions."""
import os
import requests

PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")

def query(promql: str) -> list[dict]:
    """Run an instant PromQL query -> list of {labels..., 'value': float}."""
    r = requests.get(f"{PROM_URL}/api/v1/query", params={"query": promql}, timeout=10)
    r.raise_for_status()
    out = []
    for item in r.json()["data"]["result"]:
        row = dict(item["metric"])
        row["value"] = float(item["value"][1])
        out.append(row)
    return out

def crashlooping_pods(namespace: str) -> list[dict]:
    """Pods Prometheus currently sees in CrashLoopBackOff (from kube-state-metrics)."""
    return query(f'kube_pod_container_status_waiting_reason{{namespace="{namespace}",reason="CrashLoopBackOff"}} == 1')

def restarts_last(namespace: str, minutes: int = 5) -> list[dict]:
    """How many times each pod restarted in the last N minutes (used to VERIFY a fix)."""
    return query(f'increase(kube_pod_container_status_restarts_total{{namespace="{namespace}"}}[{minutes}m])')

def cpu_reserved_vs_used(namespace: str) -> dict:
    """Green report: CPU cores reserved (requests) vs actually used, per namespace."""
    req = query(f'sum(kube_pod_container_resource_requests{{namespace="{namespace}",resource="cpu"}})')
    used = query(f'sum(rate(container_cpu_usage_seconds_total{{namespace="{namespace}",container!=""}}[5m]))')
    return {"cpu_requested_cores": req[0]["value"] if req else 0.0,
            "cpu_used_cores": used[0]["value"] if used else 0.0}
