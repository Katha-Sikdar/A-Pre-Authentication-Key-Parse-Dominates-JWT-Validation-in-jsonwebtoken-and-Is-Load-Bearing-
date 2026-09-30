#!/usr/bin/env bash
# run_rejection_breakdown.sh -- where does the cost of rejecting a forged token
# go? (revision item 4)
#
# Times bench/forged-token.js's forged_{rs,hs}_preparsed conditions (pre-parsed
# key, so no key parse is involved) with V8's default stack-trace capture and
# with --stack-trace-limit=0, which removes stack capture from every Error the
# library constructs. Same protocol as run_forged_tokens.sh: one condition per
# process, conditions interleaved within rounds.
#
# Usage: experiments/run_rejection_breakdown.sh [--rounds 10] [--iterations 10000] [--warmup 5000]
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
ROUNDS=10; ITERATIONS=10000; WARMUP=5000
IMAGES="node:18.20.8-alpine node:26.6.0-alpine psao/distro-node:ubuntu24.04"
while [ $# -gt 0 ]; do
  case "$1" in
    --rounds) ROUNDS="$2"; shift 2 ;; --iterations) ITERATIONS="$2"; shift 2 ;;
    --warmup) WARMUP="$2"; shift 2 ;; --images) IMAGES="$2"; shift 2 ;;
    *) psao::die "unknown argument: $1" ;;
  esac
done
RUN_DIR="$(psao::new_run_dir "rejection-breakdown")"
OUT="$RUN_DIR/rejection_breakdown.csv"
status=0
for env in host $IMAGES; do
  for round in $(seq 1 "$ROUNDS"); do
    for c in forged_rs_preparsed forged_hs_preparsed; do
      for stl in default 0; do
        flag=(); [ "$stl" = 0 ] && flag=(--stack-trace-limit=0)
        label="$env|stack=$stl"
        if [ "$env" = host ]; then
          node "${flag[@]}" "$PSAO_ROOT/bench/forged-token.js" --condition "$c" --iterations "$ITERATIONS" \
            --warmup "$WARMUP" --invocation "$round" --environment "$label" --out "$OUT" >/dev/null 2>&1 || status=1
        else
          docker run --rm --user "$(id -u):$(id -g)" -v "$PSAO_ROOT/bench:/bench" -v "$RUN_DIR:/out" -w /bench "$env" \
            node "${flag[@]}" /bench/forged-token.js --condition "$c" --iterations "$ITERATIONS" \
            --warmup "$WARMUP" --invocation "$round" --environment "$label" --out "/out/$(basename "$OUT")" >/dev/null 2>&1 || status=1
        fi
      done
    done
  done
  psao::log "  $env done"
done
PSAO_NAMESPACE="${PSAO_NAMESPACE:-default}" psao::write_metadata "$RUN_DIR" \
  "experiment=rejection-breakdown" "rounds=$ROUNDS" "iterations=$ITERATIONS" "warmup=$WARMUP" \
  "images=$IMAGES" "cpu_model=$(lscpu | sed -n 's/^Model name: *//p')" "nproc=$(nproc)" "needs_cluster=false" >/dev/null
psao::finish_metadata "$RUN_DIR" "$status"
psao::log "done: $OUT"
exit "$status"
