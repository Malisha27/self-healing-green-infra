#!/usr/bin/env bash
# Usage: bash scripts/experiment.sh a|b
#   a = over-provisioned, agent OFF   |   b = rightsized, agent ON
set -euo pipefail
SETUP="${1:?usage: experiment.sh a|b}"
DURATION_MIN="${DURATION_MIN:-20}"
mkdir -p results
log(){ echo "$(date -u +%H:%M:%S) [setup-$SETUP] $*"; }

log "preparing"
kubectl delete -f chaos/schedule-pod-kill.yaml --ignore-not-found
if [ "$SETUP" = "a" ]; then
  kubectl scale deploy/healing-agent -n healing-agent --replicas=0
  helm upgrade overprov-app helm/demo-app -n demo -f helm/values/overprov.yaml --wait
else
  helm upgrade overprov-app helm/demo-app -n demo -f helm/values/overprov-rightsized.yaml --wait
  kubectl scale deploy/healing-agent -n healing-agent --replicas=1
  kubectl rollout restart deploy/healing-agent -n healing-agent
  kubectl rollout status deploy/healing-agent -n healing-agent --timeout=180s
fi

log "resetting crashloop-app to HEALTHY"
helm uninstall crashloop-app -n demo --ignore-not-found
helm install crashloop-app helm/demo-app -n demo -f helm/values/crashloop.yaml \
  --set attachConfigMap=true --wait
log "warm-up 60s"; sleep 60

START=$(date -u +%s); echo "$START" > "results/setup-$SETUP.start"
log "START"
kubectl apply -f chaos/schedule-pod-kill.yaml
sleep 120

log "injecting config bug"
helm uninstall crashloop-app -n demo
helm install crashloop-app helm/demo-app -n demo -f helm/values/crashloop.yaml
sleep $(( DURATION_MIN*60 - 120 ))

kubectl delete -f chaos/schedule-pod-kill.yaml
END=$(date -u +%s); echo "$END" > "results/setup-$SETUP.end"
log "END after $(( (END-START)/60 )) min"
kubectl get pods -n demo
