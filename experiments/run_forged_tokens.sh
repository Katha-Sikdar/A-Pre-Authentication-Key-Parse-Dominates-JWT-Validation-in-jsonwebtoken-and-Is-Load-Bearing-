#!/usr/bin/env bash
# run_forged_tokens.sh -- cost of a REJECTED token, stock vs narrow fix
# (reviewer comment M7), plus the narrow fix's behavioural equivalence.
#
# For each environment (the host's own node, and each container image), runs
# bench/forged-token.js once per (condition, round), conditions interleaved
# within rounds, exactly like run_keypath_container.sh. Then runs
# bench/keypath-equivalence.js once per environment.
#
# Usage:
#   experiments/run_forged_tokens.sh [--rounds 10] [--iterations 20000]
#       [--warmup 10000] [--images "a b"] [--no-host] [--run-dir DIR]
set -euo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ROUNDS=10
ITERATIONS=20000
WARMUP=10000
HOST=1
RUN_DIR_ARG=""
IMAGES="node:18.20.8-alpine node:26.6.0-alpine psao/distro-node:ubuntu24.04"
CONDITIONS="forged_rs_string forged_rs_string_safe forged_rs_preparsed forged_hs_string forged_hs_string_safe forged_hs_preparsed probe_throws_s16 probe_throws_s256"

while [ $# -gt 0 ]; do
  case "$1" in
    --rounds) ROUNDS="$2"; shift 2 ;;
    --iterations) ITERATIONS="$2"; shift 2 ;;
    --warmup) WARMUP="$2"; shift 2 ;;
    --images) IMAGES="$2"; shift 2 ;;
    --no-host) HOST=0; shift ;;
    --run-dir) RUN_DIR_ARG="$2"; shift 2 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) psao::die "unknown argument: $1" ;;
  esac
done

if [ -n "$RUN_DIR_ARG" ]; then RUN_DIR="$RUN_DIR_ARG"; mkdir -p "$RUN_DIR"
else RUN_DIR="$(psao::new_run_dir "forged-tokens")"; fi
psao::log "run directory: $RUN_DIR"
OUT="$RUN_DIR/forged_tokens.csv"
DOCKER_UID="$(id -u):$(id -g)"
echo "environment,node_version,openssl_version,v8_version,arch,image_id" > "$RUN_DIR/environments.csv"

ident='console.log([process.version, process.versions.openssl, process.versions.v8, process.arch].join(","))'
status=0

# The patched library is built once, before any timed process, so no measured
# process pays for building it and no two processes race to write it.
node -e "require('$PSAO_ROOT/bench/keypath-patch.js').build('safe')"

envs=()
if [ "$HOST" = 1 ]; then
  envs+=("host")
  echo "host,$(node -e "$ident"),host" >> "$RUN_DIR/environments.csv"
fi
for image in $IMAGES; do
  docker image inspect "$image" >/dev/null 2>&1 || docker pull -q "$image" >/dev/null
  echo "$image,$(docker run --rm "$image" node -e "$ident"),$(docker image inspect "$image" --format '{{.Id}}')" >> "$RUN_DIR/environments.csv"
  envs+=("$image")
done

run_one() { # env condition round
  if [ "$1" = host ]; then
    node "$PSAO_ROOT/bench/forged-token.js" --condition "$2" --iterations "$ITERATIONS" \
      --warmup "$WARMUP" --invocation "$3" --environment host --out "$OUT"
  else
    docker run --rm --user "$DOCKER_UID" -v "$PSAO_ROOT/bench:/bench" -v "$RUN_DIR:/out" -w /bench "$1" \
      node /bench/forged-token.js --condition "$2" --iterations "$ITERATIONS" \
      --warmup "$WARMUP" --invocation "$3" --environment "$1" --out "/out/$(basename "$OUT")"
  fi
}

for env in "${envs[@]}"; do
  for round in $(seq 1 "$ROUNDS"); do
    for c in $CONDITIONS; do
      run_one "$env" "$c" "$round" >> "$RUN_DIR/forged_tokens.log" 2>&1 \
        || { psao::log "WARNING: $env $c round $round failed"; status=1; }
    done
    psao::log "  $env round $round/$ROUNDS"
  done
  tag="$(echo "$env" | tr '/:' '__')"
  if [ "$env" = host ]; then
    node "$PSAO_ROOT/bench/keypath-equivalence.js" --out "$RUN_DIR/equivalence_$tag.csv" \
      >> "$RUN_DIR/equivalence.log" 2>&1 || status=1
  else
    docker run --rm --user "$DOCKER_UID" -v "$PSAO_ROOT/bench:/bench" -v "$RUN_DIR:/out" -w /bench "$env" \
      node /bench/keypath-equivalence.js --out "/out/equivalence_$tag.csv" \
      >> "$RUN_DIR/equivalence.log" 2>&1 || status=1
  fi
done

if [ -z "$RUN_DIR_ARG" ]; then
  PSAO_NAMESPACE="${PSAO_NAMESPACE:-default}" psao::write_metadata "$RUN_DIR" \
    "experiment=forged-tokens" "rounds=$ROUNDS" "iterations=$ITERATIONS" "warmup=$WARMUP" \
    "images=$IMAGES" "host=$HOST" "conditions=$CONDITIONS" \
    "cpu_model=$(lscpu | sed -n 's/^Model name: *//p')" "nproc=$(nproc)" \
    "needs_cluster=false" >/dev/null
  psao::finish_metadata "$RUN_DIR" "$status"
fi
psao::log "done: $OUT"
exit "$status"
