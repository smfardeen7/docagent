#!/usr/bin/env bash
set -euo pipefail

CLUSTER="${CLUSTER:-docagent}"
OVERLAY="${OVERLAY:-ci}"
PF_PID=""

cleanup() {
  if [ -n "$PF_PID" ]; then kill "$PF_PID" 2>/dev/null || true; fi
}
on_err() {
  echo "=== FAILURE: dumping diagnostics ===" >&2
  kubectl -n docagent get pods || true
  kubectl -n docagent logs deploy/api --tail=100 || true
  kubectl -n docagent logs deploy/worker --tail=100 || true
}
trap cleanup EXIT
trap on_err ERR

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  kind create cluster --name "$CLUSTER" --wait 120s
fi

docker build -t docagent:local .
kind load docker-image docagent:local --name "$CLUSTER"

kubectl apply -k "deploy/k8s/overlays/$OVERLAY"
kubectl -n docagent rollout status deploy/redis --timeout=180s
kubectl -n docagent rollout status deploy/api --timeout=600s
kubectl -n docagent rollout status deploy/worker --timeout=600s

kubectl -n docagent port-forward svc/api 18000:8000 >/dev/null 2>&1 &
PF_PID=$!
sleep 3

python scripts/wait_and_smoke.py http://localhost:18000
