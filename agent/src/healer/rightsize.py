"""Rightsizer v1: proposes smaller CPU requests through a GitHub pull request.

It never applies anything. A human reviews the PR, merges it, and Helm applies it.
Usage (from agent/):
  PYTHONPATH=src python -m healer.rightsize --namespace demo          # report only
  PYTHONPATH=src python -m healer.rightsize --namespace demo --pr     # open a PR
"""
import argparse
import datetime as dt
import json
import math
import os
import subprocess
from pathlib import Path

import requests
import yaml

REPO = Path(os.getenv("REPO_DIR", Path(__file__).resolve().parents[3]))
VALUES_DIR = REPO / "helm" / "values"
CHART_DEFAULTS = REPO / "helm" / "demo-app" / "values.yaml"
PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")

PROTECTED_NAMESPACES = {"kube-system", "monitoring", "kepler", "chaos-mesh", "healing-agent"}
FLOOR_M = 10      # never recommend less than 10 millicores
MARGIN = 2.0      # recommendation = peak usage x 2
MIN_RATIO = 3.0   # only propose when current request >= 3x the recommendation


def log(event, **kw):
    print(json.dumps({"event": event, **kw}))


def to_millicores(value):
    s = str(value)
    return float(s[:-1]) if s.endswith("m") else float(s) * 1000


def recommend(peak_m):
    return max(FLOOR_M, math.ceil(peak_m * MARGIN))


def should_propose(current_m, rec_m):
    return current_m >= MIN_RATIO * rec_m


def current_request_m(values):
    """CPU request from the release's values file, else the chart default (Git = source of truth)."""
    defaults = yaml.safe_load(CHART_DEFAULTS.read_text()) or {}
    for src in (values, defaults):
        cpu = ((src.get("resources") or {}).get("requests") or {}).get("cpu")
        if cpu:
            return to_millicores(cpu)
    return None


def peak_usage_m(namespace, app, lookback):
    q = (f'max_over_time(max(rate(container_cpu_usage_seconds_total{{namespace="{namespace}",'
         f'container!="",pod=~"{app}-.*"}}[5m]))[{lookback}:1m])')
    r = requests.get(f"{PROM_URL}/api/v1/query", params={"query": q}, timeout=10).json()
    result = r.get("data", {}).get("result", [])
    return float(result[0]["value"][1]) * 1000 if result else None


def analyse(namespace, lookback):
    rows = []
    for f in sorted(VALUES_DIR.glob("*.yaml")):
        app = f"{f.stem}-app"  # helm/values/overprov.yaml -> release overprov-app
        values = yaml.safe_load(f.read_text()) or {}
        cur = current_request_m(values)
        peak = peak_usage_m(namespace, app, lookback)
        if cur is None or peak is None:
            log("skip", file=f.name, reason=f"no request set or no usage data for {app}")
            continue
        rec = recommend(peak)
        row = {"file": f, "app": app, "current_m": cur, "peak_m": peak, "rec_m": rec,
               "propose": should_propose(cur, rec)}
        rows.append(row)
        log("analysis", app=app, file=f.name, current=f"{cur:.0f}m", peak=f"{peak:.2f}m",
            recommend=f"{rec}m", propose=row["propose"])
    return rows


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, check=True,
                          capture_output=True, text=True).stdout.strip()


def open_pr(rows, namespace, lookback):
    props = [r for r in rows if r["propose"]]
    if not props:
        log("nothing_to_propose")
        return
    if git("status", "--porcelain"):
        log("blocked", reason="working tree not clean, commit or stash first")
        return
    base = git("rev-parse", "--abbrev-ref", "HEAD")
    branch = "rightsize/" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    git("switch", "-c", branch)
    try:
        for r in props:
            values = yaml.safe_load(r["file"].read_text()) or {}
            values.setdefault("resources", {}).setdefault("requests", {})["cpu"] = f"{r['rec_m']}m"
            r["file"].write_text(yaml.safe_dump(values, sort_keys=False))
            git("add", str(r["file"].relative_to(REPO)))
        title = f"rightsize({namespace}): lower CPU requests for {len(props)} app(s)"
        git("commit", "-m", title)
        git("push", "-u", "origin", branch)
        table = "\n".join(f"| {r['app']} | {r['current_m']:.0f}m | {r['peak_m']:.2f}m | **{r['rec_m']}m** |"
                          for r in props)
        body = f"""Proposed by the rightsizer (`healer.rightsize`). **Nothing was applied.** A human decides.

| App | Requested now | Peak used (last {lookback}) | Proposed |
|---|---|---|---|
{table}

Method: peak CPU from Prometheus x {MARGIN:g} safety margin, never below {FLOOR_M}m, only when the current request is at least {MIN_RATIO:g}x the proposal. Memory and limits are not touched.

Caveat: only {lookback} of data. In production use 7-30 days to catch weekly peaks.

After merging: `helm upgrade <release> helm/demo-app -n {namespace} -f helm/values/<file>.yaml`
"""
        try:
            url = subprocess.run(["gh", "pr", "create", "--base", base, "--head", branch,
                                  "--title", title, "--body", body],
                                 cwd=REPO, check=True, capture_output=True, text=True).stdout.strip()
            log("pr_opened", url=url, branch=branch)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log("pr_manual", branch=branch, hint="open the PR on GitHub from this branch",
                error=str(e)[:200])
    finally:
        git("switch", base)


def main():
    p = argparse.ArgumentParser(description="Propose CPU rightsizing via a pull request")
    p.add_argument("--namespace", default="demo")
    p.add_argument("--lookback", default="24h")
    p.add_argument("--pr", action="store_true", help="open a PR (default: report only)")
    a = p.parse_args()
    if a.namespace in PROTECTED_NAMESPACES:
        log("blocked", reason=f"{a.namespace} is protected")
        return
    rows = analyse(a.namespace, a.lookback)
    if a.pr:
        open_pr(rows, a.namespace, a.lookback)
    else:
        log("report_only", hint="re-run with --pr to open a pull request")


if __name__ == "__main__":
    main()
