# Runbook: Pod crashes because a configuration value is missing
## Symptoms
- Pod in CrashLoopBackOff, restarts keep increasing
- Logs contain "<VAR> not set", "missing environment variable", "KeyError", "config not found"
## Root cause
The app needs an environment variable that is not present in the container. Often a ConfigMap
or Secret holding the value EXISTS in the namespace but is not referenced by the Deployment.
## Fix
1. Check ConfigMaps in the namespace for a key matching the missing variable.
2. If found: attach it to the Deployment (envFrom configMapRef). Action: attach_configmap. Risk: low.
3. If not found: do NOT invent values. Escalate to a human. Action: escalate.
## Verify
Rollout completes, new pod Ready, restart count stops increasing.
