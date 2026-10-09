"""Self-healing agent.
Loop: detect -> gather evidence -> diagnose -> guardrails -> heal -> verify -> report."""
import argparse, datetime, json, os, re, time
from healer import k8s_tools as k8s, prom_tools as prom

PROTECTED_NAMESPACES = {"kube-system", "monitoring", "kepler", "local-path-storage"}
ALLOWED_ACTIONS = {"attach_configmap", "escalate"}
MAX_ATTEMPTS = 2
attempts: dict[str, int] = {}

def log(event: str, **kw) -> None:
    """One JSON line per event = structured log (easy to search, graph, and show on slides)."""
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%SZ")
    print(json.dumps({"ts": ts, "event": event, **kw}), flush=True)

# 1. DETECT
def detect(ns: str) -> list[dict]:
    try:
        prom_seen = {p["pod"] for p in prom.crashlooping_pods(ns)}
    except Exception:
        prom_seen = set()   # Prometheus down? Still work using the Kubernetes API.
    sick = k8s.find_unhealthy_pods(ns)
    for p in sick:
        p["seen_by_prometheus"] = p["pod"] in prom_seen
    return sick

# 2. GATHER EVIDENCE
def gather_evidence(pod: dict, ns: str) -> dict:
    return {"pod": pod["pod"], "namespace": ns, "reason": pod["reason"], "restarts": pod["restarts"],
            "deployment": k8s.get_deployment_for_pod(pod["pod"], ns),
            "logs": k8s.get_pod_logs(pod["pod"], ns),
            "configmaps": k8s.list_configmaps(ns)}

# 3. DIAGNOSE (Phase 3: simple rules. Phase 4: replaced by LLM + RAG, same output format)
def diagnose(ev: dict) -> dict:
    m = re.search(r"\b([A-Z][A-Z0-9_]+) not set", ev["logs"])
    if m:
        var = m.group(1)
        for cm, keys in ev["configmaps"].items():
            if var in keys:
                return {"root_cause": f"Env var {var} is missing; ConfigMap '{cm}' contains it but is not attached",
                        "action": "attach_configmap", "params": {"configmap": cm},
                        "risk": "low", "confidence": 0.9, "brain": "rules"}
        return {"root_cause": f"Env var {var} is missing and no ConfigMap provides it",
                "action": "escalate", "params": {}, "risk": "high", "confidence": 0.6, "brain": "rules"}
    return {"root_cause": "Unknown failure pattern", "action": "escalate", "params": {},
            "risk": "high", "confidence": 0.3, "brain": "rules"}

# 4. GUARDRAILS (the AI proposes, the guardrails decide)
def guardrails(plan: dict, ev: dict, mode: str) -> tuple[bool, str]:
    if ev["namespace"] in PROTECTED_NAMESPACES:      return False, "protected namespace"
    if plan["action"] not in ALLOWED_ACTIONS:        return False, f"action '{plan['action']}' not in allowlist"
    if plan["action"] == "escalate":                 return False, "escalated to a human"
    if not ev["deployment"]:                         return False, "pod has no Deployment owner"
    if attempts.get(ev["deployment"], 0) >= MAX_ATTEMPTS: return False, "max heal attempts reached"
    if mode == "dry-run":                            return False, "dry-run mode: plan only, no action"
    if mode == "auto" and plan["risk"] != "low":     return False, "auto mode only runs low-risk plans"
    if mode == "ask":
        ans = input(f"\n>>> Apply '{plan['action']}' {plan['params']} to {ev['deployment']}? [y/N] ")
        if ans.strip().lower() != "y":               return False, "human rejected"
    return True, "approved"

# 5. HEAL
def heal(plan: dict, ev: dict) -> None:
    if plan["action"] == "attach_configmap":
        k8s.attach_configmap(ev["deployment"], ev["namespace"], plan["params"]["configmap"])

# 6. VERIFY
def verify(ev: dict) -> bool:
    rolled_out = k8s.wait_for_rollout(ev["deployment"], ev["namespace"], timeout=90)
    still_sick = [p for p in k8s.find_unhealthy_pods(ev["namespace"]) if p["app"] == ev["deployment"]]
    return rolled_out and not still_sick

def run_once(ns: str, mode: str) -> None:
    sick = detect(ns)
    if not sick:
        log("all_healthy", namespace=ns); return
    handled = set()
    for pod in sick:
        t0 = time.time()
        log("detected", pod=pod["pod"], reason=pod["reason"], restarts=pod["restarts"],
            seen_by_prometheus=pod["seen_by_prometheus"])
        ev = gather_evidence(pod, ns)
        if ev["deployment"] in handled:
            continue
        handled.add(ev["deployment"])
        log("evidence", deployment=ev["deployment"], logs=ev["logs"].strip()[-200:], configmaps=ev["configmaps"])
        plan = diagnose(ev)
        log("diagnosis", **plan)
        ok, why = guardrails(plan, ev, mode)
        log("guardrails", approved=ok, reason=why, mode=mode)
        if not ok:
            continue
        attempts[ev["deployment"]] = attempts.get(ev["deployment"], 0) + 1
        heal(plan, ev)
        log("healing", action=plan["action"], deployment=ev["deployment"])
        healed = verify(ev)
        log("verified" if healed else "verify_failed", deployment=ev["deployment"],
            mttr_seconds=round(time.time() - t0, 1))

def main() -> None:
    ap = argparse.ArgumentParser(description="Self-healing green infra agent")
    ap.add_argument("--namespace", default=os.getenv("WATCH_NAMESPACE", "demo"))
    ap.add_argument("--mode", default=os.getenv("APPROVAL_MODE", "dry-run"), choices=["dry-run", "ask", "auto"])
    ap.add_argument("--once", action="store_true", help="run one check and exit")
    ap.add_argument("--interval", type=int, default=20, help="seconds between checks")
    a = ap.parse_args()
    log("agent_started", namespace=a.namespace, mode=a.mode)
    while True:
        run_once(a.namespace, a.mode)
        if a.once:
            break
        time.sleep(a.interval)

if __name__ == "__main__":
    main()
