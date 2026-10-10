#!/usr/bin/env bash
# Usage: bash scripts/results.sh  (needs Prometheus port-forward on :9090)
set -euo pipefail
PROM=${PROM_URL:-http://localhost:9090}
NS='namespace=~"demo|healing-agent"'
q(){ curl -s --get "$PROM/api/v1/query" --data-urlencode "query=$1" --data-urlencode "time=$2" \
  | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "nan")'; }
for S in a b; do
  START=$(cat results/setup-$S.start); END=$(cat results/setup-$S.end); D=$((END-START))
  RES=$(q "avg_over_time(sum(kube_pod_container_resource_requests{$NS,resource=\"cpu\"})[${D}s:30s])" $END)
  USED=$(q "avg_over_time(sum(rate(container_cpu_usage_seconds_total{$NS,container!=\"\"}[2m]))[${D}s:30s])" $END)
  AVAIL=$(q "avg_over_time((sum(kube_deployment_status_replicas_available{namespace=\"demo\"}) / sum(kube_deployment_spec_replicas{namespace=\"demo\"}))[${D}s:30s]) * 100" $END)
  python3 - "$S" "$D" "$RES" "$USED" "$AVAIL" <<'PY'
import sys
s, d = sys.argv[1], float(sys.argv[2]); res, used, avail = map(float, sys.argv[3:])
W, CO2 = 4, 0.7
kwh_year = res * W * 8760 / 1000
print(f"Setup {s.upper()}: {d/60:.0f} min | reserved {res:.3f} cores | used {used:.4f} | "
      f"waste {res/used:.0f}x | availability {avail:.1f}% | est. {res*W:.2f} W = "
      f"{kwh_year:.1f} kWh/yr = {kwh_year*CO2:.1f} kg CO2/yr")
PY
done | tee results/summary.txt
