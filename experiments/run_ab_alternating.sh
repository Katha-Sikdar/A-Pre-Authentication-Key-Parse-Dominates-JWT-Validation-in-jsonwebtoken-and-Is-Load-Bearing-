#!/usr/bin/env bash
# run_ab_alternating.sh -- the in-situ A/B repeated as alternating windows
# (reviewer comment M3). NOT run for the submitted revision: it needs the
# Kubernetes testbed in testbed/. See TODO_EXPERIMENTS.md, item M3.
#
# Runs --pairs pairs of windows. Within each pair the order of the two arms
# (validation enabled / disabled) is randomised with a recorded seed, so neither
# arm systematically follows the other. Each window is one open-loop step at
# --rps for --duration, driven by run_openloop_ramp.sh exactly as the original
# INSITU-AB-authmode-* runs were, with the arm selected by PSAO_AUTH_MODE on the
# same deployment and image. Host load is recorded per window by the ramp
# runner's metadata. Pin k6 to cores the cluster does not use with --k6-cpus
# (taskset list, e.g. "3") or run it from another machine with --base-url.
#
# Output: data/runs/<ts>-ab-alternating/{order.csv, window-NN-<arm>/...}
# Analyse: python3 -m analysis.ab_alternating --run data/runs/<ts>-ab-alternating
#
# Usage:
#   experiments/run_ab_alternating.sh [--pairs 5] [--rps 200] [--duration 3m]
#       [--seed 20261001] [--k6-cpus 3] [--base-url https://localhost]
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
PAIRS=5; RPS=200; DUR=3m; SEED=20261001; K6_CPUS=""; BASE_URL="https://localhost"
while [ $# -gt 0 ]; do
  case "$1" in
    --pairs) PAIRS="$2"; shift 2 ;; --rps) RPS="$2"; shift 2 ;;
    --duration) DUR="$2"; shift 2 ;; --seed) SEED="$2"; shift 2 ;;
    --k6-cpus) K6_CPUS="$2"; shift 2 ;; --base-url) BASE_URL="$2"; shift 2 ;;
    *) psao::die "unknown argument: $1" ;;
  esac
done
psao::require kubectl
RUN_DIR="$(psao::new_run_dir "ab-alternating")"
echo "window,pair,arm,started_at_utc" > "$RUN_DIR/order.csv"
order="$(python3 -c "
import random; r=random.Random($SEED)
print(' '.join(' '.join(r.sample(['jwt','none'],2)) for _ in range($PAIRS)))")"
w=0
for arm in $order; do
  w=$((w + 1)); pair=$(( (w + 1) / 2 ))
  kubectl -n default set env deploy/service-a-deployment PSAO_AUTH_MODE="$arm" >/dev/null
  kubectl -n default rollout status deploy/service-a-deployment --timeout=180s >/dev/null
  sleep 30   # let the new pod reach steady state before the window opens
  wdir="$RUN_DIR/window-$(printf %02d $w)-$arm"
  echo "$w,$pair,$arm,$(date -u +%FT%TZ)" >> "$RUN_DIR/order.csv"
  # A signed token stays on the wire in BOTH arms, as in the original A/B: the
  # disabled arm removes only the handler's jwt.verify() call.
  prefix=(); [ -n "$K6_CPUS" ] && prefix=(taskset -c "$K6_CPUS")
  "${prefix[@]}" "$PSAO_ROOT/experiments/run_openloop_ramp.sh" --scenario "AB-$arm" \
    --max-rps "$RPS" --step-rps "$RPS" --step-duration "$DUR" --base-url "$BASE_URL" \
    --run-dir "$wdir"
done
kubectl -n default set env deploy/service-a-deployment PSAO_AUTH_MODE=jwt >/dev/null
psao::write_metadata "$RUN_DIR" "experiment=ab-alternating" "pairs=$PAIRS" "rps=$RPS" \
  "duration=$DUR" "seed=$SEED" "k6_cpus=$K6_CPUS" "base_url=$BASE_URL" >/dev/null
psao::finish_metadata "$RUN_DIR" 0
psao::log "done: $RUN_DIR"
