#!/usr/bin/env bash
# Delete the local cluster (frees RAM). Recreate anytime with setup-cluster.sh
kind delete cluster --name green-infra
