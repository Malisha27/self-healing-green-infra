#!/usr/bin/env bash
# Codespaces: give kind nodes internet access (iptables legacy vs nft mismatch).
# Run after every codespace restart or cluster re-create.
set -euo pipefail
BR="br-$(docker network inspect kind -f '{{.Id}}' | cut -c1-12)"
SUBNET="$(docker network inspect kind -f '{{range .IPAM.Config}}{{.Subnet}} {{end}}' | tr ' ' '\n' | grep -m1 '\.')"
echo "kind bridge: $BR  subnet: $SUBNET"
sudo iptables-legacy -t nat -C POSTROUTING -s "$SUBNET" ! -o "$BR" -j MASQUERADE 2>/dev/null \
  || sudo iptables-legacy -t nat -A POSTROUTING -s "$SUBNET" ! -o "$BR" -j MASQUERADE
sudo iptables-legacy -C FORWARD -i "$BR" -j ACCEPT 2>/dev/null || sudo iptables-legacy -I FORWARD -i "$BR" -j ACCEPT
sudo iptables-legacy -C FORWARD -o "$BR" -j ACCEPT 2>/dev/null || sudo iptables-legacy -I FORWARD -o "$BR" -j ACCEPT
echo -n "Internet from node: "
docker exec green-infra-control-plane curl -s -o /dev/null -w "%{http_code}\n" -m 5 https://quay.io || echo "STILL BLOCKED"
