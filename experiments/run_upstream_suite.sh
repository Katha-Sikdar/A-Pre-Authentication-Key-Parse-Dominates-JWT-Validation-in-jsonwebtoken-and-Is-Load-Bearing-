#!/usr/bin/env bash
# run_upstream_suite.sh -- the library's own test suite against each variant of
# verify.js, on several runtimes (revision item 1).
#
# Clones jsonwebtoken at tag v9.0.3, installs its dev dependencies once, and for
# every (runtime, variant, extra-tests) runs `mocha` over the library's test/
# directory, recording the full output and the passing/failing counts.
#
#   variants  stock    unmodified verify.js
#             safe     the narrow fix (declared alg HS* AND plain string secret)
#             keyonly  plain string secret alone, whatever the declared alg
#             naive    declared alg HS* alone (deliberately unsafe control)
#   extra     none, or upstream/verify-keypath.tests.js added to test/
#
# Usage:
#   experiments/run_upstream_suite.sh [--images "a b"] [--no-host] [--run-dir DIR]
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

IMAGES="node:18.20.8-alpine node:26.6.0-alpine psao/distro-node:ubuntu24.04"
HOST=1; RUN_DIR_ARG=""
VARIANTS="stock safe keyonly naive"
while [ $# -gt 0 ]; do
  case "$1" in
    --images) IMAGES="$2"; shift 2 ;;
    --no-host) HOST=0; shift ;;
    --run-dir) RUN_DIR_ARG="$2"; shift 2 ;;
    *) psao::die "unknown argument: $1" ;;
  esac
done
if [ -n "$RUN_DIR_ARG" ]; then RUN_DIR="$RUN_DIR_ARG"; mkdir -p "$RUN_DIR"
else RUN_DIR="$(psao::new_run_dir "upstream-suite-variants")"; fi
WORK="$RUN_DIR/work"; mkdir -p "$WORK"
psao::log "run directory: $RUN_DIR"

git clone -q --depth 1 --branch v9.0.3 https://github.com/auth0/node-jsonwebtoken "$WORK/jsonwebtoken"
( cd "$WORK/jsonwebtoken" && git rev-parse HEAD > "$RUN_DIR/tag_commit.txt" && npm install --silent --no-audit --no-fund >/dev/null )
cp "$WORK/jsonwebtoken/verify.js" "$WORK/verify.stock.js"
sha256sum "$WORK/verify.stock.js" | cut -d' ' -f1 > "$RUN_DIR/verify_stock_sha256.txt"

# Build each variant from bench/'s copy (byte-identical to the tag's verify.js;
# keypath-patch.js refuses to build if the expected block is absent).
cmp -s "$WORK/verify.stock.js" "$PSAO_ROOT/bench/node_modules/jsonwebtoken/verify.js" \
  || psao::die "bench/node_modules/jsonwebtoken/verify.js differs from the v9.0.3 tag"
for v in safe keyonly naive; do
  d="$(node -e "console.log(require('$PSAO_ROOT/bench/keypath-patch.js').build('$v'))")"
  cp "$d/verify.js" "$WORK/verify.$v.js"
done
sha256sum "$WORK"/verify.*.js | sed "s#$WORK/##" > "$RUN_DIR/variant_sha256.txt"

echo "runtime,node_version,openssl_version,variant,extra_tests,passing,failing,pending,failing_titles" > "$RUN_DIR/summary.csv"
ident='console.log([process.version, process.versions.openssl].join(","))'

run_suite() { # runtime variant extra
  local rt="$1" v="$2" extra="$3" tag out
  cp "$WORK/verify.$v.js" "$WORK/jsonwebtoken/verify.js"
  rm -f "$WORK/jsonwebtoken/test/zz-verify-keypath.tests.js"
  [ "$extra" = keypath ] && cp "$PSAO_ROOT/upstream/verify-keypath.tests.js" "$WORK/jsonwebtoken/test/zz-verify-keypath.tests.js"
  tag="$(echo "$rt" | tr '/:' '__')"; out="$RUN_DIR/${tag}_${v}_${extra}.txt"
  if [ "$rt" = host ]; then
    ( cd "$WORK/jsonwebtoken" && ./node_modules/.bin/mocha --reporter spec ) > "$out" 2>&1 || true
    ver="$(node -e "$ident")"
  else
    docker run --rm --user "$(id -u):$(id -g)" -v "$WORK/jsonwebtoken:/jwtlib" -w /jwtlib "$rt" \
      node ./node_modules/.bin/mocha --reporter spec > "$out" 2>&1 || true
    ver="$(docker run --rm "$rt" node -e "$ident")"
  fi
  local pass fail pend titles
  pass="$(grep -Eo '^ +[0-9]+ passing' "$out" | grep -Eo '[0-9]+' || echo 0)"
  fail="$(grep -Eo '^ +[0-9]+ failing' "$out" | grep -Eo '[0-9]+' || echo 0)"
  pend="$(grep -Eo '^ +[0-9]+ pending' "$out" | grep -Eo '[0-9]+' || echo 0)"
  titles="$(grep -E '^ +[0-9]+\) ' "$out" | sed -E 's/^ +[0-9]+\) //' | sort -u | tr '\n' '|' | sed 's/"/'"'"'/g' || true)"
  echo "$rt,$ver,$v,$extra,$pass,$fail,$pend,\"$titles\"" >> "$RUN_DIR/summary.csv"
  psao::log "  $rt $v $extra: $pass passing, $fail failing"
}

rts=(); [ "$HOST" = 1 ] && rts+=(host)
for i in $IMAGES; do rts+=("$i"); done
for rt in "${rts[@]}"; do
  for v in $VARIANTS; do
    for extra in none keypath; do run_suite "$rt" "$v" "$extra"; done
  done
done
cp "$WORK/verify.stock.js" "$WORK/jsonwebtoken/verify.js"
rm -rf "$WORK/jsonwebtoken/node_modules"
if [ -z "$RUN_DIR_ARG" ]; then
  PSAO_NAMESPACE="${PSAO_NAMESPACE:-default}" psao::write_metadata "$RUN_DIR" \
    "experiment=upstream-suite-variants" "images=$IMAGES" "host=$HOST" "variants=$VARIANTS" \
    "cpu_model=$(lscpu | sed -n 's/^Model name: *//p')" "nproc=$(nproc)" "needs_cluster=false" >/dev/null
  psao::finish_metadata "$RUN_DIR" 0
fi
psao::log "done: $RUN_DIR/summary.csv"
