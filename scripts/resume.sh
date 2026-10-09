#!/usr/bin/env bash
# Run after every codespace restart: wakes the cluster and restores networking.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
docker start green-infra-control-plane >/dev/null 2>&1 || true
echo "Waiting 60s for the API server to load permissions..."; sleep 60
bash "$(dirname "$0")/fix-network.sh"
kubectl get nodes
echo "Pods not Running (ideally none):"; kubectl get pods -A --no-headers | grep -v Running || echo "  all good ✅"
