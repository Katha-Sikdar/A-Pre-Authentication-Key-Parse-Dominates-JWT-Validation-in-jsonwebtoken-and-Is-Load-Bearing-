# Replication package: a pre-authentication key parse in `jsonwebtoken`

This repository holds the measurements, instrumentation, harnesses and analysis
code behind a study of where the per-request cost of JSON Web Token (JWT)
validation goes in the Node.js library `jsonwebtoken` (v9.0.3).

**Finding in one paragraph.** When `jsonwebtoken` is given an HMAC shared secret
as a string, `verify()` first offers it to `crypto.createPublicKey()` and only
falls back to `createSecretKey()` after that parse fails. The discarded parse,
not the signature, is the largest part of the validation cost. It runs before
the algorithm check and before signature verification. Its price is set by the
OpenSSL release the runtime bundles: from C, the same calls cost 394.4 µs on
OpenSSL 3.0.16 and 8.447 µs on 3.5.8. The parse is also load-bearing for the
library's key-confusion defence, so the obvious optimisation is unsafe. The
narrow fix in `upstream/` preserves that defence.

## The one rule

Every reported number is **generated** from a file under `data/runs/` or
`survey/`. None is typed by hand. The two generators below rebuild all of them.

```sh
mkdir -p macros
python3 -m analysis.make_keypath_macros  --out macros/keypath_macros.tex \
                                         --map macros/keypath_macros_provenance.csv
python3 -m analysis.make_revision_macros --out macros/revision_macros.tex
```

Each macro file has a companion `*_provenance.csv` naming, for every value, the
run file it was read from.

## Layout

| Path | Contents |
|---|---|
| `data/runs/` | Every run, including ones that failed; `data/runs/INDEX.md` describes each |
| `analysis/` | Statistics and the macro generators |
| `bench/` | Harnesses: `keypath-mechanism.js` (one condition per process), `exception-cost.js`, `c/openssl-probe.c`, `libs/` (cross-library harnesses in JavaScript, Python, Go and Java) |
| `experiments/` | Drivers: host decomposition, container runtime matrix, OpenSSL builds, C probe, exception baseline, cross-library comparison, in-situ ramps |
| `survey/` | Prevalence survey of public call sites and its corpus manifest |
| `upstream/` | `verify.js.patch` (the narrow fix), its tests, a minimal reproduction, and the issue as filed |
| `figures/` | Figure scripts |
| `instrumentation/`, `controller/`, `scenarios/` | Service instrumentation and the harness of an earlier sidecar-offloading study whose runs are kept in `data/runs/` |
| `testbed/` | The measured service (`service-a`), its peer (`service-b`), Kubernetes and Istio manifests, and k6 load tests |
| `docs/DATA_SCHEMA.md` | Column definitions for the run files |

## Reproducing the measurements

**Requirements.** Python ≥ 3.10 with `requirements.txt`, Node.js, and Docker.
The C probe also needs a C compiler and `make` to build the OpenSSL releases.
The in-situ runs need a Kubernetes cluster with Istio and k6.

```sh
make setup                                   # .venv plus Python and Node dependencies

# Host decomposition of verify() and the container runtime matrix
experiments/run_keypath_mechanism.sh
experiments/run_keypath_container.sh

# The failed parse issued from C against OpenSSL releases built from source,
# the V8 exception baseline, and the cross-library comparison
experiments/build_openssl_versions.sh
experiments/fetch_node_runtimes.sh
experiments/run_revision_suite.sh            # C probe + exception cost + cross-library

# In-situ measurement (needs the cluster in testbed/)
experiments/run_openloop_ramp.sh
```

Each run writes a new timestamped directory under `data/runs/` together with a
`run_metadata.json` recording host, runtime, image digests and tool versions.

## Testbed

Apple-silicon host on macOS 26.5.2 (arm64). Host microbenchmarks ran under
Node.js v26.6.0. Container measurements ran in Docker Desktop's single-node
Kubernetes (v1.32.2). The service is Express 5.1.0 with `jsonwebtoken` 9.0.3 on
`node:18-alpine`: one replica with an Istio sidecar behind an NGINX ingress,
and k6 v2.2.0 driving load on the same machine. The x86_64 repetitions ran on a
shared cloud VM (4 vCPUs). The exact versions of each run are in its
`run_metadata.json`.

## The survey corpus is not redistributed

The call sites examined are third-party source. `survey/data/corpus_manifest.csv`
pins every file by content hash and repository commit instead.

## Responsible disclosure

The defect was reported to the maintainers as auth0/node-jsonwebtoken#1046. The
key-confusion behaviour discussed is a publicly documented attack class. Here it
is exercised only through the library's own test suite, and no exploitation
recipe is included.

## License

MIT. See `LICENSE`. The development JWT secret in `testbed/service-a` is a
placeholder for local testing only.
