"""Kubernetes 'tools': the agent's eyes (read) and hands (act).
Each function = one thing a human SRE would do with kubectl."""
import time
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Inside the cluster -> use the pod's service account. On my laptop/codespace -> use ~/.kube/config.
try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

core = client.CoreV1Api()   # pods, logs, configmaps
apps = client.AppsV1Api()   # deployments, replicasets

BAD_REASONS = {"CrashLoopBackOff", "Error", "ImagePullBackOff", "ErrImagePull",
               "CreateContainerConfigError", "OOMKilled"}

# ---------- EYES (read-only) ----------
def find_unhealthy_pods(namespace: str) -> list[dict]:
    """Like: kubectl get pods  -> keep only the sick ones."""
    sick = []
    for p in core.list_namespaced_pod(namespace).items:
        for s in (p.status.container_statuses or []):
            reason = None
            if s.state.waiting and s.state.waiting.reason in BAD_REASONS:
                reason = s.state.waiting.reason
            elif s.last_state.terminated and s.last_state.terminated.reason == "OOMKilled":
                reason = "OOMKilled"
            if reason:
                sick.append({"pod": p.metadata.name, "namespace": namespace, "reason": reason,
                             "restarts": s.restart_count, "app": (p.metadata.labels or {}).get("app")})
    return sick

def get_pod_logs(pod: str, namespace: str, tail: int = 20) -> str:
    """Like: kubectl logs --previous  (falls back to current logs)."""
    for previous in (True, False):
        try:
            return core.read_namespaced_pod_log(pod, namespace, previous=previous, tail_lines=tail)
        except ApiException:
            continue
    return "<no logs available>"

def list_configmaps(namespace: str) -> dict[str, list[str]]:
    """Like: kubectl get configmaps  -> {name: [keys]} (values hidden: may be sensitive)."""
    return {cm.metadata.name: sorted((cm.data or {}).keys())
            for cm in core.list_namespaced_config_map(namespace).items
            if not cm.metadata.name.startswith("kube-root-ca")}

def get_deployment_for_pod(pod: str, namespace: str) -> str | None:
    """Pod -> ReplicaSet -> Deployment (follow the 'owner' chain)."""
    p = core.read_namespaced_pod(pod, namespace)
    for ref in p.metadata.owner_references or []:
        if ref.kind == "ReplicaSet":
            rs = apps.read_namespaced_replica_set(ref.name, namespace)
            for r in rs.metadata.owner_references or []:
                if r.kind == "Deployment":
                    return r.name
    return None

# ---------- HANDS (change things) ----------
def attach_configmap(deployment: str, namespace: str, configmap: str) -> None:
    """Like: kubectl set env --from=configmap  but using envFrom (clean, one line)."""
    dep = apps.read_namespaced_deployment(deployment, namespace)
    container = dep.spec.template.spec.containers[0].name
    patch = {"spec": {"template": {"spec": {"containers": [
        {"name": container, "envFrom": [{"configMapRef": {"name": configmap}}]}]}}}}
    apps.patch_namespaced_deployment(deployment, namespace, patch)

def wait_for_rollout(deployment: str, namespace: str, timeout: int = 90) -> bool:
    """Like: kubectl rollout status  -> True if all new pods became ready in time."""
    end = time.time() + timeout
    while time.time() < end:
        d = apps.read_namespaced_deployment(deployment, namespace)
        st, want = d.status, d.spec.replicas or 1
        if (st.observed_generation or 0) >= d.metadata.generation and \
           (st.updated_replicas or 0) == want and (st.available_replicas or 0) == want and \
           (st.replicas or 0) == want:
            return True
        time.sleep(3)
    return False
