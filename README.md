# Self-Healing Infra is Green Infra 🌱

> Using AI to cut Kubernetes waste without breaking things.

Prometheus tells you what broke. An AI agent figures out why and fixes it. Guardrails make sure it doesn't do anything stupid. And once your cluster can heal itself, you can stop over-provisioning "just in case".

**Self-healing is the means. Green is the result.**

**Status:** complete and working end to end: closed-loop healing, dashboard, before/after experiment, and a rightsizer that opens its own pull request. Built in public, one commit at a time.

![Grafana: break, heal, rightsize](docs/screenshots/22-grafana-full-story.png)

---

## The problem

Teams over-provision Kubernetes. Big CPU requests, extra replicas, all "just in case". And honestly I get it, nobody wants a 2 AM call because a pod is crash-looping.

But that fear costs a lot. On my own demo cluster:

- **16.7%** CPU actually used vs **60%** CPU requested (whole cluster)
- In the demo namespace: **0.6 cores reserved vs ~0.002 used = 200-300x over-provisioned**

Reserved CPU nobody uses still needs servers switched on. That's money, energy and CO2 for nothing.

The funny part: most incidents are repeats (missing config, OOM, bad rollout) and the fix is already written in a runbook somewhere. A human still has to wake up, read logs and follow it.

## What it does

A closed loop that runs inside the cluster:

```mermaid
flowchart LR
    A[Prometheus alert] -->|webhook| B[Detect]
    B --> C[Diagnose<br/>LLM + RAG]
    C --> D[Guardrails]
    D -->|approved| E[Heal]
    D -->|blocked| H[Escalate to human]
    E --> F[Verify]
    F -->|healthy| G[Learn]
    F -->|still broken| H
```

1. **Detect** - Prometheus fires an alert (e.g. `PodCrashLooping`), Alertmanager calls the agent's webhook.
2. **Diagnose** - the agent collects evidence (logs, ConfigMaps, restarts), RAG pulls the matching runbook + past incidents from ChromaDB, and the LLM returns a JSON fix plan (root cause, action, risk, confidence).
3. **Guardrails** - the plan has to pass safety checks before anything runs.
4. **Heal** - apply the fix (e.g. attach the missing ConfigMap).
5. **Verify** - wait for the rollout and check the pod is actually healthy. No fake success.
6. **Learn** - only verified fixes get saved back into memory, so next time its own experience is the top match.

Once healing is fast and reliable, you can **rightsize**: give apps what they really use, not what fear says.

## Results

### Healing speed (MTTR = mean time to recovery)

| Who fixed it | MTTR |
|---|---|
| Nobody (the original broken pod) | sat broken **6.5 hours**, 23 restarts |
| Agent, rules brain, human approves (ask mode) | **11.9 s** |
| Agent, LLM brain, fully auto | **4.4 s** |
| Full closed loop in-cluster (alert → webhook → LLM → heal → verify) | **14.4 s** |

### Before / after experiment

Same workload, same failures (Chaos Mesh kills a pod every 5 min + a config bug injected at minute 2), 20 min each.

| Metric | Setup A: over-provisioned, no agent | Setup B: rightsized + agent | Change |
|---|---|---|---|
| CPU reserved (avg) | 0.601 cores | 0.176 cores | **-71%** |
| Availability (avg) | 77.5% | 98.3% | **+20.8 pts** |
| Config bug | never healed (still broken after 18 min) | healed, agent MTTR **7.8 s** (~2 min bug → healthy incl. alert wait) | fixed vs not fixed |
| Over-provisioning | 173x | 22x | **-87%** |
| Est. power | 2.40 W | 0.71 W | **-71%** |
| Est. energy (if run for a year) | 21.1 kWh/yr | 6.2 kWh/yr | **-71%** |
| Est. CO2 (if run for a year) | 14.7 kg/yr | 4.3 kg/yr | **-71%** |

**Greener AND more reliable, at the same time.** Numbers come from `scripts/results.sh` (Prometheus averages over each exact window, saved in `results/`).

Honest notes:
- Setup B's numbers **include the agent's own CPU** (`healing-agent` namespace). The healer isn't free, and it's counted.
- "Used" CPU is higher in B (0.0079 vs 0.0035 cores) because a healthy app plus the agent actually do work, while a crash-looping app mostly sits in back-off.
- B isn't 100% because pod-kills still cause short dips, and the alert waits a bit (`for:`) before firing, to avoid false alarms.
- Tiny absolute numbers (it's a demo namespace). The **ratio** is the point.

### Plot twist: waste blocked the healing 🤯

While building the dashboard I broke the app on purpose. The agent diagnosed it right (confidence 0.95) and applied the right fix in seconds... and then the fixed pod sat **Pending for 7+ minutes**:

```
0/1 nodes are available: 1 Insufficient cpu.
```

The node had 2 cores, all **booked**, while almost nothing was **used**. The over-provisioned app was holding CPU it never touched, so the healing pod couldn't get a seat. The agent did the safe thing: `verify_failed` (honest), one retry, then `max heal attempts reached` and stopped.

I rightsized the waster with Helm (2 × 250m → 1 × 25m), the pending pod got scheduled instantly, availability went back to 100%.

- reserved CPU **0.65 → ~0.12 cores**
- over-provisioning **334x → 29x**
- estimated power **~2.6 W → ~0.5 W**

We didn't add capacity. We freed it.

## Architecture

![Architecture](docs/architecture.png)

Editable source: [`docs/architecture.drawio`](docs/architecture.drawio) (open at app.diagrams.net).

| Piece | What it does here |
|---|---|
| **kind** | Local Kubernetes cluster (Kubernetes IN Docker), runs in GitHub Codespaces |
| **Helm** | Installs everything: monitoring stack, Kepler, Chaos Mesh, demo apps |
| **Prometheus + Alertmanager** | Metrics, alert rules, webhook to the agent |
| **Grafana** | Dashboard: availability, CPU reserved vs used, waste ratio, estimated power, alert annotations |
| **Kepler** | Per-pod energy share (CNCF project) |
| **Chaos Mesh** | Breaks things on purpose, on a schedule |
| **Python agent** | The loop: tools, guardrails, webhook server |
| **Groq (`openai/gpt-oss-120b`)** | The LLM brain. Model name lives in config, not code |
| **ChromaDB** | RAG memory: runbooks + verified past incidents |

### Tech stack

| Area | Tools |
|---|---|
| Platform | GitHub Codespaces, Docker, Kubernetes (kind), Helm |
| Observability | Prometheus, Alertmanager, Grafana, Kepler |
| Chaos | Chaos Mesh |
| AI | Python agent, RAG with ChromaDB (all-MiniLM-L6-v2 embeddings), LLM on Groq (`openai/gpt-oss-120b`) |
| GitOps-style changes | Helm values in Git, rightsizer opens PRs with `gh` |
| Testing | pytest (14 tests, no cluster or LLM needed) |

## How it works

| File | Job |
|---|---|
| `agent/src/healer/k8s_tools.py` | The agent's eyes and hands: find unhealthy pods, read logs, list ConfigMaps, find the owning Deployment, patch it, wait for rollout |
| `agent/src/healer/prom_tools.py` | PromQL queries: crash-looping pods, restarts, CPU reserved vs used |
| `agent/src/healer/rag.py` | ChromaDB: index runbooks, retrieve similar ones, remember verified incidents |
| `agent/src/healer/llm.py` | Sends evidence + retrieved runbooks to the LLM, validates the JSON plan |
| `agent/src/healer/main.py` | The loop: detect → evidence → diagnose → guardrails → heal → verify → learn. Modes: `dry-run`, `ask`, `auto` |
| `agent/src/healer/server.py` | Webhook: `POST /alert` from Alertmanager, `GET /healthz` |
| `runbooks/*.md` | What a human would do: missing config, OOMKilled, image pull, over-provisioned |
| `monitoring/rules/demo-alerts.yaml` | Alert rules. `heal="true"` routes to the agent |

Detection uses **multiple signals** (waiting reason, exit code, OOMKilled, restarts + not ready), because a pod's status is just a snapshot and a crash-looping pod is "Running" for 1-2 seconds every cycle.

## Safety: why the AI can't do anything stupid

- **Action allowlist** - the agent can only do actions it knows. Anything else → escalate.
- **Hallucination guard** - if the LLM names a ConfigMap that isn't in the evidence, the plan is blocked.
- **Confidence + risk gate** - auto mode needs confidence ≥ 0.8 and low risk. Otherwise ask a human.
- **Max 2 attempts** - no infinite heal loops (this actually triggered for real, see the plot twist).
- **Protected namespaces** - `kube-system` and friends are untouchable.
- **Verify before claiming success** - and ignore pods that are already on their way out.
- **Learn only verified fixes** - no memory poisoning.
- **Deterministic LLM** - `temperature: 0` + JSON mode.
- **Least-privilege RBAC** - the agent's ServiceAccount can read pods/logs/ConfigMaps and patch Deployments, **only in `demo`**. It can't delete pods, read Secrets or touch `kube-system` (checked with `kubectl auth can-i --as=...`).
- **Unit tested** - `agent/tests/test_safety.py`, 10 tests, no cluster or LLM needed.
- **Rightsizing is NOT automatic** - healing restores desired state (safe, reversible). Changing capacity is a business decision, so it stays human-approved and goes through Helm/Git. The `NamespaceOverProvisioned` alert is `heal="false"` on purpose.

### The rightsizer: it proposes, a human merges

`agent/src/healer/rightsize.py` reads each app's CPU request **from Git** (`helm/values/*.yaml`, the source of truth), asks Prometheus for the **peak** real usage, and proposes **peak × 2** (never below 10m). It only proposes when the saving is big (current ≥ 3× the proposal). Then it opens a **GitHub pull request** with the evidence. It never applies anything.

```bash
cd agent
PYTHONPATH=src python -m healer.rightsize --namespace demo        # report only
PYTHONPATH=src python -m healer.rightsize --namespace demo --pr   # open a PR
```

![Rightsizer PR](docs/screenshots/26-rightsizer-pr.png)

First real run: `overprov-app` 250m → **10m** (peak used 2.46m), `healthy-app` and `crashloop-app` 50m → 10m. Guardrails: refuses protected namespaces, refuses a dirty working tree, never touches memory or limits. Caveat: only ~24h of data here, production should look at 7-30 days. The PR is opened with my GitHub credentials; in production it would be a bot account or GitHub App with only PR permissions.

## How the energy numbers are measured (honestly)

Cloud VMs (and Codespaces) don't expose CPU power sensors (RAPL), so Kepler runs with its fake meter here. That means:

- ❌ I never show Kepler's absolute watts as measured results.
- ✅ **Real:** CPU reserved vs used (Prometheus), and each pod's % share of power (Kepler splits power by real CPU use).
- ✅ **Estimated, method disclosed:** energy = real CPU core-hours × **~4 W per vCPU**, CO2 = kWh × **~0.7 kg/kWh** (India grid). Same idea as tools like Cloud Carbon Footprint.
- Headline is always **relative**: "X% less CPU reserved → X% less estimated energy, SLO still met".

Reserved CPU counts as energy because servers are bought and kept on for what's reserved, not what's used.

## Quick start

Tested on GitHub Codespaces (2-core works but it's tight, 4-core is comfier).

```bash
# 0. secrets (never commit .env)
cp .env.example .env   # add GROQ_API_KEY

# 1. cluster + Prometheus/Grafana/Alertmanager + Kepler
bash scripts/setup-cluster.sh
kubectl apply -f monitoring/rules/demo-alerts.yaml

# 2. Chaos Mesh (kind uses containerd)
helm repo add chaos-mesh https://charts.chaos-mesh.org && helm repo update
helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh -n chaos-mesh --create-namespace \
  -f chaos/chaos-mesh-values.yaml --wait

# 3. demo apps
docker build -t demo-app:v1 apps/demo-app
kind load docker-image demo-app:v1 --name green-infra
helm upgrade --install healthy-app   helm/demo-app -n demo --create-namespace -f helm/values/healthy.yaml
helm upgrade --install overprov-app  helm/demo-app -n demo -f helm/values/overprov.yaml
helm upgrade --install crashloop-app helm/demo-app -n demo -f helm/values/crashloop.yaml

# 4. the agent, in-cluster
docker build -f agent/Dockerfile -t healing-agent:v1 .
kind load docker-image healing-agent:v1 --name green-infra
kubectl apply -f k8s/agent/agent.yaml
set -a; source .env; set +a
kubectl create secret generic groq-api -n healing-agent \
  --from-literal=GROQ_API_KEY="$GROQ_API_KEY" --dry-run=client -o yaml | kubectl apply -f -
```

Then watch it heal:

```bash
kubectl get pods -n demo -w
kubectl logs -n healing-agent deploy/healing-agent -f
```

**Grafana:** `kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80` → Dashboards → New → Import → `monitoring/dashboards/self-healing-green-infra.json`.

**Break it again:**

```bash
helm uninstall crashloop-app -n demo && helm install crashloop-app helm/demo-app -n demo -f helm/values/crashloop.yaml
```

**Run the experiment:** `bash scripts/experiment.sh a` then `bash scripts/experiment.sh b`.

**Run the agent locally** (handy for debugging):

```bash
cd agent && uv venv --python 3.12 .venv && source .venv/bin/activate && uv pip install -r requirements.txt
PYTHONPATH=src python -m healer.main --namespace demo --mode dry-run --once   # or ask / auto, --brain llm|rules
PYTHONPATH=src python -m pytest tests -q
```

**After a Codespace restart:** `bash scripts/resume.sh` (starts the node, fixes kind's network, shows unhappy pods).

## Repo layout

```
agent/            Python agent (src/healer), Dockerfile, tests
apps/demo-app/    Flask demo app (can crash on purpose)
chaos/            Chaos Mesh values + experiments
helm/demo-app/    Helm chart for the demo apps
helm/values/      healthy, overprov, overprov-rightsized, crashloop
k8s/              kind config + agent manifests (RBAC, Deployment, Service)
monitoring/       Prometheus/Kepler values, alert rules, Grafana dashboard
runbooks/         Knowledge the agent retrieves (RAG)
scripts/          setup, resume, fix-network, teardown, experiment
docs/             architecture + screenshots
results/          experiment windows + summary
```

## Lessons learned

Real stuff I hit while building this:

- **Waste can block healing.** `Insufficient cpu` with ~0.2% CPU actually used. Booked ≠ used.
- **Config drift is sneaky.** A manual `kubectl set env` wasn't undone by `helm upgrade`, because Helm only manages the fields it owns (server-side apply). Do changes through Helm/Git.
- **Pod status is a snapshot.** My first detector said "all healthy" during a CrashLoopBackOff (race condition). Fix: check several signals.
- **Fixing one bug can expose another.** Verify said "failed" while the fix worked, because the old pod was still dying. Fix: ignore terminating pods + wait to settle. A false "failed" is safer than a false "success".
- **Never hard-code a model name.** Groq retired the model I started with overnight. Keep it in config.
- **Helm accepts unknown values silently.** Kepler ignored my old-style setting and crash-looped. Check the app's own logs, and the docs for *your* version.
- **kind in Codespaces loses internet on restart** (iptables legacy vs nft). `scripts/fix-network.sh` fixes it.
- **Special characters in a Grafana panel title** (÷, ×) broke the queries with a 400. Plain titles only.

## Talk

Built for my talk **"Self-Healing Infra is Green Infra: Using AI to Cut Kubernetes Waste Without Breaking Things"** at the **Cloud Native Pune x Docker Pune** meetup, **17 Oct 2026**.

## Author

**Malisha Gavali** - [LinkedIn](https://linkedin.com/in/malisha) | [GitHub](https://github.com/Malisha27)

## License

MIT