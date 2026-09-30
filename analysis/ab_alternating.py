#!/usr/bin/env python3
"""ab_alternating.py -- analyse run_ab_alternating.sh output (reviewer M3).

For each pair of windows, CPU per request (millicores / achieved rps * 1000,
the same computation as the original A/B) is computed per arm, and the
within-pair difference enabled - disabled is taken. Reports the median
difference over pairs with a 95% percentile bootstrap interval over pairs
(10,000 resamples, fixed seed), the per-pair values, validation's share of
per-request CPU, and host load per window.

  python3 -m analysis.ab_alternating --run data/runs/<ts>-ab-alternating
Writes <run>/ab_alternating.json.
"""
import argparse, csv, json, re
from pathlib import Path
import numpy as np

LOAD = re.compile(r'load averages?: *([0-9.]+)')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--run', required=True)
    run = Path(ap.parse_args().run)
    order = list(csv.DictReader((run / 'order.csv').open()))
    per, windows = {}, []
    for o in order:
        d = run / f"window-{int(o['window']):02d}-{o['arm']}"
        r = next(csv.DictReader((d / 'openloop_ramp.csv').open()))
        cpu = float(r['cpu_app_millicores']) / float(r['achieved_rps']) * 1000.0
        meta = json.loads((d / 'run_metadata.json').read_text())
        m = LOAD.search((meta.get('host') or {}).get('uptime_at_run_start') or '')
        windows.append({'window': int(o['window']), 'pair': int(o['pair']), 'arm': o['arm'],
                        'cpu_us_per_request': cpu, 'host_load1': float(m.group(1)) if m else None})
        per.setdefault(int(o['pair']), {})[o['arm']] = cpu
    pairs = sorted(p for p, v in per.items() if {'jwt', 'none'} <= set(v))
    diff = np.array([per[p]['jwt'] - per[p]['none'] for p in pairs])
    share = np.array([100 * (per[p]['jwt'] - per[p]['none']) / per[p]['jwt'] for p in pairs])
    rng = np.random.default_rng(20260917)
    idx = rng.integers(0, len(diff), size=(10000, len(diff)))
    ci = np.percentile(np.median(diff[idx], axis=1), [2.5, 97.5]).tolist()
    out = {'pairs': len(pairs), 'median_diff_us': float(np.median(diff)), 'ci95': ci,
           'per_pair_diff_us': diff.tolist(), 'median_share_pct': float(np.median(share)),
           'windows': windows}
    (run / 'ab_alternating.json').write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps({k: v for k, v in out.items() if k != 'windows'}, indent=2))


if __name__ == '__main__':
    main()
