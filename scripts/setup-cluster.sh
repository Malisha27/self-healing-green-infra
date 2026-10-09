#!/usr/bin/env bash
# Day 1: create kind cluster + Prometheus/Grafana/Alertmanager + Kepler (fake meter)
# Run from repo root inside WSL2 Ubuntu (or Codespaces):  bash scripts/setup-cluster.sh
set -euo pipefail

KIND_VERSION="v0.27.0"
KEPLER_CHART_VERSION="${KEPLER_CHART_VERSION:-0.12.0}"

need() { command -v "$1" >/dev/null 2>&1; }

echo "==> 1/6 Checking Docker"
docker info >/dev/null 2>&1 || { echo "Docker is not running. Start Docker Desktop (WSL2 integration ON) and retry."; exit 1; }

echo "==> 2/6 Installing CLI tools if missing (kind, kubectl, helm)"
mkdir -p "$HOME/.local/bin"; export PATH="$HOME/.local/bin:$PATH"
if ! need kind; then
  curl -sLo "$HOME/.local/bin/kind" "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-amd64"
  chmod +x "$HOME/.local/bin/kind"
fi
if ! need kubectl; then
  curl -sLo "$HOME/.local/bin/kubectl" "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
  chmod +x "$HOME/.local/bin/kubectl"
fi
if ! need helm; then
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | HELM_INSTALL_DIR="$HOME/.local/bin" USE_SUDO=false bash
fi

echo "==> 3/6 Creating kind cluster 'green-infra'"
if kind get clusters | grep -qx green-infra; then
  echo "Cluster already exists, skipping."
else
  kind create cluster --config k8s/kind/kind-config.yaml
fi
kubectl cluster-info --context kind-green-infra

echo "==> 4/6 Installing Prometheus + Grafana + Alertmanager (kube-prometheus-stack)"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo update >/dev/null
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f monitoring/kube-prometheus-values.yaml --wait --timeout 10m

echo "==> 5/6 Restoring kind node internet (Codespaces)"
bash scripts/fix-network.sh
echo "==> 5b/6 Installing Kepler ${KEPLER_CHART_VERSION} (falls back to fake meter in VMs)"
helm upgrade --install kepler oci://quay.io/sustainable_computing_io/charts/kepler \
  --version "${KEPLER_CHART_VERSION}" -n kepler --create-namespace \
  -f monitoring/kepler-values.yaml --wait --timeout 5m

echo "==> 6/6 Status"
kubectl get pods -A
echo
echo "Done. Next:"
echo "  Grafana:    kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80   -> http://localhost:3000 (admin/admin)"
echo "  Prometheus: kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090 -> http://localhost:9090"
echo "  In Prometheus, type 'kepler_' in the query box. If metrics appear, Day 1 is DONE."
