"""Unit tests for the agent's safety logic. No cluster or LLM needed (Kubernetes calls are faked)."""
import sys, types
# Fake the kubernetes + chromadb modules so tests run anywhere (CI, laptop) without a cluster.
for name in ["kubernetes", "kubernetes.client", "kubernetes.config", "kubernetes.client.rest", "chromadb"]:
    sys.modules.setdefault(name, types.ModuleType(name))
k = sys.modules["kubernetes"]; k.client = sys.modules["kubernetes.client"]; k.config = sys.modules["kubernetes.config"]
k.config.ConfigException = Exception
k.config.load_incluster_config = lambda: None
k.client.CoreV1Api = k.client.AppsV1Api = lambda: None
sys.modules["kubernetes.client.rest"].ApiException = Exception
sys.modules["chromadb"].PersistentClient = lambda path: types.SimpleNamespace(get_or_create_collection=lambda n: None)

from healer import main, llm

EV = {"pod": "p", "namespace": "demo", "reason": "CrashLoopBackOff", "restarts": 5, "deployment": "crashloop-app",
      "logs": "[crashloop-app] FATAL: DB_URL not set.", "configmaps": {"crashloop-app-config": ["DB_URL"]}}
GOOD = {"root_cause": "x", "action": "attach_configmap", "params": {"configmap": "crashloop-app-config"},
        "risk": "low", "confidence": 0.95}

def setup_function(): main.attempts.clear()

# --- rules brain ---
def test_rules_find_missing_configmap():
    plan = main.diagnose_rules(EV)
    assert plan["action"] == "attach_configmap" and plan["params"]["configmap"] == "crashloop-app-config"

def test_rules_escalate_when_no_configmap_has_the_key():
    assert main.diagnose_rules({**EV, "configmaps": {}})["action"] == "escalate"

# --- LLM output validation (hallucination guard) ---
def test_hallucinated_configmap_is_blocked():
    assert llm.validate({**GOOD, "params": {"configmap": "made-up"}}, EV)["action"] == "escalate"

def test_unknown_action_is_blocked():
    assert llm.validate({**GOOD, "action": "delete_namespace"}, EV)["action"] == "escalate"

# --- guardrails ---
def test_dry_run_never_acts():
    assert main.guardrails(GOOD, EV, "dry-run")[0] is False

def test_auto_allows_low_risk_high_confidence():
    assert main.guardrails(GOOD, EV, "auto") == (True, "approved")

def test_auto_blocks_low_confidence():
    assert main.guardrails({**GOOD, "confidence": 0.5}, EV, "auto")[0] is False

def test_auto_blocks_medium_risk():
    assert main.guardrails({**GOOD, "risk": "medium"}, EV, "auto")[0] is False

def test_protected_namespace_is_never_touched():
    assert main.guardrails(GOOD, {**EV, "namespace": "kube-system"}, "auto")[0] is False

def test_max_attempts_stops_heal_loops():
    main.attempts["crashloop-app"] = main.MAX_ATTEMPTS
    assert main.guardrails(GOOD, EV, "auto")[0] is False
