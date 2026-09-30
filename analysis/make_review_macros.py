#!/usr/bin/env python3
"""make_review_macros.py -- LaTeX macros for values added in response to the
JSS review. Same rules as make_keypath_macros.py: every value is read from a
file under data/runs/ or survey/, nothing is typed, and a value whose source is
absent is emitted as \\PLACEHOLDER{name} (red in the PDF), never guessed.

Sources:
  data/runs/2026-09-17T08-42-17Z-keypath-mechanism/keypath_stats.json
      bootstrap settings of every reported interval (minor 9)
  data/runs/INSITU-AB-authmode-{jwt,none}/openloop_ramp.csv
      validation as a share of per-request application CPU (M2)
  data/runs/*-keypath-runtime-matrix whose environments.csv lists psao/distro-node
      distribution-packaged Node.js linked to the system OpenSSL (M2)
  data/runs/*-forged-tokens/forged_tokens.csv, equivalence_*.csv
      cost of rejected tokens, stock vs narrow fix; behavioural equivalence (M7)
  survey/libsurvey/data/frame_*.json, scan_*_summary.json, scan_*.csv,
  survey/libsurvey/data/adjudication_*.csv
      the npm library survey (M1)

Usage:
  python3 -m analysis.make_review_macros --out macros/review_macros.tex \\
      [--map macros/review_macros_provenance.csv]
"""
from __future__ import annotations
import argparse, csv, json, re, sys
from pathlib import Path

import numpy as np
import pandas as pd

from analysis import keypath_stats as ks

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / 'data' / 'runs'
LIB = ROOT / 'survey' / 'libsurvey' / 'data'
NUM: dict[str, str] = {}
SRC: dict[str, str] = {}
MISSING: list[str] = []


def put(name, value, source, fmt='{:.2f}'):
    if re.search(r'\d', name):
        raise SystemExit(f'macro name contains a digit: {name}')
    if value is None:
        MISSING.append(name); return
    NUM[name] = fmt.format(value) if isinstance(value, float) else str(value)
    SRC[name] = str(Path(source).relative_to(ROOT))


def sig(x):
    """Three significant figures, as the existing macros use."""
    if x == 0:
        return '0'
    from math import floor, log10
    d = max(0, 2 - int(floor(log10(abs(x)))))
    return f'{x:.{d}f}'


def latest(pattern, must_contain=None):
    for d in sorted(RUNS.glob(pattern), reverse=True):
        env = d / 'environments.csv'
        if must_contain is None or (env.exists() and must_contain in env.read_text()):
            return d
    return None


# --- bootstrap settings (minor 9) --------------------------------------------
mech = RUNS / '2026-09-17T08-42-17Z-keypath-mechanism' / 'keypath_stats.json'
if mech.exists():
    js = json.loads(mech.read_text())
    put('BootstrapResamples', f"{js['bootstrap_resamples']:,}".replace(',', '{,}'), mech)
else:
    MISSING.append('BootstrapResamples')

# --- A/B: validation as a share of per-request CPU (M2) -----------------------
ab = {arm: RUNS / f'INSITU-AB-authmode-{arm}' / 'openloop_ramp.csv' for arm in ('jwt', 'none')}
if all(p.exists() for p in ab.values()):
    r = {arm: next(csv.DictReader(p.open())) for arm, p in ab.items()}
    per = {arm: float(x['cpu_app_millicores']) / float(x['achieved_rps']) * 1000.0 for arm, x in r.items()}
    delta = (float(r['jwt']['cpu_app_millicores']) - float(r['none']['cpu_app_millicores'])) \
        / float(r['jwt']['achieved_rps']) * 1000.0
    put('AbCpuShareOfRequestPct', 100.0 * delta / per['jwt'], ab['jwt'], '{:.0f}')
    put('AbCpuRatio', per['jwt'] / per['none'], ab['jwt'], '{:.2f}')
else:
    MISSING += ['AbCpuShareOfRequestPct', 'AbCpuRatio']

# --- distribution-packaged Node.js (M2) --------------------------------------
DISTRO = {'psao/distro-node:ubuntu24.04': 'DistroUbuntu',
          'node:18.20.8-alpine': 'DistroRefEighteen',
          'node:26.6.0-alpine': 'DistroRefTwentySix'}
drun = latest('*-keypath-runtime-matrix', 'psao/distro-node')
if drun is not None:
    stats = drun / 'keypath_stats.json'
    if not stats.exists():
        ks.main(['--run', str(drun)])
    js = json.loads(stats.read_text())
    envs = {r['image']: r for r in csv.DictReader((drun / 'environments.csv').open())}
    md = json.loads((drun / 'run_metadata.json').read_text()) if (drun / 'run_metadata.json').exists() else {}
    put('DistroCaptured', drun.name[:10], drun)
    for image, pre in DISTRO.items():
        e = js['environments'].get(image)
        if not e:
            MISSING.append(pre); continue
        c = e['conditions']
        put(pre + 'Node', envs[image]['node_version'].lstrip('v'), drun / 'environments.csv')
        put(pre + 'Openssl', envs[image]['openssl_version'], drun / 'environments.csv')
        for cond, name in (('probe_throws', 'ProbeThrows'), ('probe_succeeds', 'ProbeSucceeds'),
                           ('jwt_hs_string', 'JwtString'), ('jwt_hs_preparsed', 'JwtPreparsed'),
                           ('jwt_hs_string_safe', 'JwtStringSafe'),
                           ('jwt_hs_string_keyonly', 'JwtStringKeyonly'),
                           ('jwt_sign_string', 'SignString'), ('jwt_sign_preparsed', 'SignPreparsed')):
            if cond in c:
                put(pre + name, sig(c[cond]['median_of_medians_us']), stats)
        pen = (e.get('contrasts') or {}).get('string_key_penalty_hs256')
        if pen:
            put(pre + 'Penalty', sig(pen['median_diff_us']), stats)
            put(pre + 'PenaltyCiLo', sig(pen['ci95'][0]), stats)
            put(pre + 'PenaltyCiHi', sig(pen['ci95'][1]), stats)
    put('DistroRounds', (md.get('run_parameters') or {}).get('rounds'), drun / 'run_metadata.json')
    put('DistroCalls', f"{int((md.get('run_parameters') or {}).get('iterations')):,}".replace(',', '{,}')
        if (md.get('run_parameters') or {}).get('iterations') else None, drun / 'run_metadata.json')
    put('DistroCpus', (md.get('run_parameters') or {}).get('docker_cpus'), drun / 'run_metadata.json')
    df = pd.read_csv(drun / 'keypath_mechanism.csv')
    rp = md.get('run_parameters') or {}
    n_cond = len((rp.get('conditions') or '').split())
    put('DistroConditions', n_cond, drun / 'run_metadata.json')
    put('DistroFailedInvocations', int(len(DISTRO) * n_cond * int(rp.get('rounds', 0)) - len(df)),
        drun / 'keypath_mechanism.csv')
    rng_d = np.random.default_rng(ks.SEED)
    for image, pre in DISTRO.items():
        sub = df[df['environment'] == image]
        d = ks.paired_diff(sub, 'jwt_sign_string', 'jwt_sign_preparsed', rng_d)
        if d:
            put(pre + 'SignPenalty', sig(d['median_diff_us']), drun / 'keypath_mechanism.csv')
            put(pre + 'SignPenaltyCiLo', sig(d['ci95'][0]), drun / 'keypath_mechanism.csv')
            put(pre + 'SignPenaltyCiHi', sig(d['ci95'][1]), drun / 'keypath_mechanism.csv')
else:
    MISSING.append('DistroUbuntu')

# --- forged tokens and equivalence (M7) --------------------------------------
FENV = {'host': 'Host', 'node:18.20.8-alpine': 'Eighteen', 'node:26.6.0-alpine': 'TwentySix',
        'psao/distro-node:ubuntu24.04': 'Ubuntu'}
FCOND = {'forged_rs_string': 'RsString', 'forged_rs_string_safe': 'RsSafe',
         'forged_rs_preparsed': 'RsPreparsed', 'forged_hs_string': 'HsString',
         'forged_hs_string_safe': 'HsSafe', 'forged_hs_preparsed': 'HsPreparsed',
         'probe_throws_s16': 'ProbeSixteen', 'probe_throws_s256': 'ProbeTwoFiftySix',
         'forged_rs_string_keyonly': 'RsKeyonly', 'forged_hs_string_keyonly': 'HsKeyonly'}
frun = latest('*-forged-tokens')
if frun is not None and (frun / 'forged_tokens.csv').exists():
    df = pd.read_csv(frun / 'forged_tokens.csv')
    rng = np.random.default_rng(ks.SEED)
    envs = {r['environment']: r for r in csv.DictReader((frun / 'environments.csv').open())}
    put('ForgedInvocations', int(df.groupby(['environment', 'condition']).size().min()), frun / 'forged_tokens.csv')
    put('ForgedCalls', int(df['n'].iloc[0]), frun / 'forged_tokens.csv')
    for env, pre in FENV.items():
        sub = df[df['environment'] == env]
        if sub.empty:
            MISSING.append('Forged' + pre); continue
        put('Forged' + pre + 'Openssl', envs[env]['openssl_version'], frun / 'environments.csv')
        put('Forged' + pre + 'Node', envs[env]['node_version'].lstrip('v'), frun / 'environments.csv')
        for cond, name in FCOND.items():
            v = sub[sub['condition'] == cond]['median_us'].to_numpy()
            if v.size == 0:
                MISSING.append('Forged' + pre + name); continue
            put('Forged' + pre + name, sig(float(np.median(v))), frun / 'forged_tokens.csv')
        for a, b, name in (('forged_rs_string_safe', 'forged_rs_preparsed', 'RsSafeOverPreparsed'),
                           ('forged_hs_string_safe', 'forged_hs_preparsed', 'HsSafeOverPreparsed')):
            d = ks.paired_diff(sub, a, b, rng)
            if d:
                put('Forged' + pre + name, sig(d['median_diff_us']), frun / 'forged_tokens.csv')
    put('ForgedCpuModel', (json.loads((frun / 'run_metadata.json').read_text()).get('run_parameters') or {}).get('cpu_model')
        if (frun / 'run_metadata.json').exists() else None, frun / 'run_metadata.json')
    eq = sorted(frun.glob('equivalence_*.csv'))
    if eq:
        cases = diffs = 0
        for p in eq:
            rows = list(csv.DictReader(p.open()))
            cases += len(rows)
            diffs += sum(1 for r in rows if r['identical'] != 'true')
        put('EquivCasesPerRuntime', len(list(csv.DictReader(eq[0].open()))), eq[0])
        put('EquivRuntimes', len(eq), frun)
        put('EquivDiffs', diffs, frun)
        dk = [sum(1 for r in csv.DictReader(p.open()) if r.get('identical_keyonly') != 'true') for p in eq]
        put('EquivDiffsKeyonly', sum(dk) if all('identical_keyonly' in (next(csv.DictReader(p.open())) or {}) for p in eq) else None, frun)
        kinds = {r['key_material'] for r in csv.DictReader(eq[0].open())}
        put('EquivKeyKinds', len(kinds), eq[0])
else:
    MISSING.append('Forged')

# --- library test suite for each variant (item 1) ----------------------------
srun = latest('*-upstream-suite-variants')
if srun is not None and (srun / 'summary.csv').exists():
    rows = list(csv.DictReader((srun / 'summary.csv').open()))
    put('SuiteVariantRuntimes', len({r['runtime'] for r in rows}), srun / 'summary.csv')
    for v, name in (('stock', 'Stock'), ('safe', 'Safe'), ('keyonly', 'Keyonly'), ('naive', 'Naive')):
        for extra, tag in (('none', ''), ('keypath', 'Plus')):
            rr = [r for r in rows if r['variant'] == v and r['extra_tests'] == extra]
            p_, f_ = {r['passing'] for r in rr}, {r['failing'] for r in rr}
            # One value only if every runtime agrees; otherwise the macro is missing.
            put('SuiteVar' + name + tag + 'Passing', p_.pop() if len(p_) == 1 else None, srun / 'summary.csv')
            put('SuiteVar' + name + tag + 'Failing', f_.pop() if len(f_) == 1 else None, srun / 'summary.csv')
    put('SuiteVarCommit', (srun / 'tag_commit.txt').read_text().strip()[:7], srun / 'tag_commit.txt')
else:
    MISSING.append('SuiteVar')

# --- rejection breakdown: stack capture (item 4) ------------------------------
rrun = latest('*-rejection-breakdown')
if rrun is not None and (rrun / 'rejection_breakdown.csv').exists():
    df = pd.read_csv(rrun / 'rejection_breakdown.csv')
    for env, pre in FENV.items():
        for cond, c in (('forged_rs_preparsed', 'Rs'), ('forged_hs_preparsed', 'Hs')):
            for stl, st in (('default', 'Stack'), ('0', 'NoStack')):
                v = df[(df['environment'] == f'{env}|stack={stl}') & (df['condition'] == cond)]['median_us'].to_numpy()
                put('Rej' + pre + c + st, sig(float(np.median(v))) if v.size else None, rrun / 'rejection_breakdown.csv')
    put('RejInvocations', int(df.groupby(['environment', 'condition']).size().min()), rrun / 'rejection_breakdown.csv')
else:
    MISSING.append('Rej')

# --- host VM run for Figure 9 (item 1) ----------------------------------------
vrun = None
for d in sorted(RUNS.glob('*-keypath-mechanism'), reverse=True):
    if (d / 'process_versions.json').exists():
        vrun = d; break
if vrun is not None:
    st = vrun / 'keypath_stats.json'
    if not st.exists():
        ks.main(['--run', str(vrun)])
    js = json.loads(st.read_text())
    (env, e), = js['environments'].items()
    pv = json.loads((vrun / 'process_versions.json').read_text())
    put('VmbNode', pv['node'], vrun / 'process_versions.json')
    put('VmbOpenssl', pv['openssl'], vrun / 'process_versions.json')
    for cond, name in (('jwt_hs_string', 'JwtString'), ('jwt_hs_preparsed', 'JwtPreparsed'),
                       ('jwt_hs_string_safe', 'JwtStringSafe'), ('jwt_hs_string_keyonly', 'JwtStringKeyonly')):
        put('Vmb' + name, sig(e['conditions'][cond]['median_of_medians_us']) if cond in e['conditions'] else None, st)
else:
    MISSING.append('Vmb')

# --- machines (item 3) --------------------------------------------------------
def meta(d):
    p = RUNS / d / 'run_metadata.json'
    return json.loads(p.read_text()) if p.exists() else {}
_mac = meta('2026-09-17T08-42-17Z-keypath-mechanism')
_mx = meta('2026-09-17T08-57-13Z-keypath-runtime-matrix')
_vma = meta('2026-09-24T17-10-07Z-openssl-c-probe')
_vmam = meta('2026-09-24T17-44-01Z-keypath-runtime-matrix')
_vmb = meta(drun.name) if drun is not None else {}
def plat(m):
    return (m.get('host') or {}).get('platform', '')
put('MachMacOs', re.sub(r'^macOS-([0-9.]+)-.*', r'macOS \1', plat(_mac)) or None, RUNS / '2026-09-17T08-42-17Z-keypath-mechanism/run_metadata.json')
put('MachDockerCpus', (_mx.get('run_parameters') or {}).get('docker_cpus'), RUNS / '2026-09-17T08-57-13Z-keypath-runtime-matrix/run_metadata.json')
_cpu_a = (_vma.get('host') or {}).get('cpu_model') or (_vma.get('run_parameters') or {}).get('cpu_model') or ''
put('MachVmaCpu', re.sub(r'\(R\)', '', _cpu_a).replace('  ', ' ') or None, RUNS / '2026-09-24T17-10-07Z-openssl-c-probe/run_metadata.json')
put('MachVmaCpus', (_vmam.get('run_parameters') or {}).get('docker_cpus'), RUNS / '2026-09-24T17-44-01Z-keypath-runtime-matrix/run_metadata.json')
put('MachVmaKernel', re.sub(r'^Linux-([^-]+-[^-]+-[^-]+)-.*', r'\1', plat(_vma)) or None, RUNS / '2026-09-24T17-10-07Z-openssl-c-probe/run_metadata.json')
put('MachVmaLibc', re.sub(r'.*with-glibc', 'glibc ', plat(_vma)) or None, RUNS / '2026-09-24T17-10-07Z-openssl-c-probe/run_metadata.json')
if frun is not None:
    _cpu_b = (json.loads((frun / 'run_metadata.json').read_text()).get('run_parameters') or {}).get('cpu_model') or ''
    put('MachVmbCpu', re.sub(r'\(R\)', '', _cpu_b).replace('  ', ' ') or None, frun / 'run_metadata.json')
    put('MachVmbCpus', (json.loads((frun / 'run_metadata.json').read_text()).get('run_parameters') or {}).get('nproc'), frun / 'run_metadata.json')
    put('MachVmbKernel', re.sub(r'^Linux-([^-]+-[^-]+-[^-]+)-.*', r'\1', plat(json.loads((frun / 'run_metadata.json').read_text()))) or None, frun / 'run_metadata.json')

_mb = RUNS / 'MACHINE-vm-b-2026-09-30' / 'machine.txt'
if _mb.exists():
    _t = _mb.read_text()
    _m = re.search(r'PRETTY_NAME="([^"]+)"', _t)
    put('MachVmbOs', _m.group(1) if _m else None, _mb)
else:
    MISSING.append('MachVmbOs')

# --- Ubuntu 24.04 nodejs package status (item 5) -------------------------------
ub = RUNS / '2026-09-30-ubuntu-nodejs-support' / 'apt_nodejs.txt'
if ub.exists():
    t = ub.read_text()
    m = re.search(r'nodejs \| ([^ ]+) \| \S+ (\S+)/(\S+) ', t)
    put('UbuntuNodejsPkg', m.group(1).replace('~', '\\textasciitilde{}') if m else None, ub)
    put('UbuntuNodejsComponent', m.group(3) if m else None, ub)
    put('UbuntuNodejsCaptured', t.strip().splitlines()[0][:10], ub)
else:
    MISSING.append('UbuntuNodejs')

# --- npm library survey (M1) -------------------------------------------------
for frame, pre in (('jwt', 'LibJwt'), ('crypto', 'LibCrypto')):
    fj, sj = LIB / f'frame_{frame}.json', LIB / f'scan_{frame}_summary.json'
    if not fj.exists() or not sj.exists():
        MISSING.append(pre); continue
    f, s = json.loads(fj.read_text()), json.loads(sj.read_text())
    put(pre + 'Threshold', f"{f['min_weekly_downloads']:,}".replace(',', '{,}'), fj)
    put(pre + 'Captured', f['captured_at_utc'][:10], fj)
    put(pre + 'Returned', f['packages_returned'], fj)
    put(pre + 'InFrame', f['packages_in_frame'], fj)
    put(pre + 'Scanned', s['packages_scanned'], sj)
    put(pre + 'Failed', s['packages_failed'], sj)
    put(pre + 'Files', s['js_files'], sj)
    put(pre + 'Unparsed', s['js_files_unparsed'], sj)
    put(pre + 'PkgsAnyHit', s['packages_with_any_hit'], sj)
    put(pre + 'PkgsShapeA', s['packages_with_shape_A'], sj)
    adj = LIB / f'adjudication_{frame}.csv'
    if adj.exists():
        rows = list(csv.DictReader(adj.open()))
        put(pre + 'Adjudicated', len(rows), adj)
        conf = [r for r in rows if r['verdict'] == 'failing_parse_type_test']
        put(pre + 'Confirmed', len(conf), adj)
        put(pre + 'ConfirmedPkgs', len({r['package'] for r in conf}), adj)
        put(pre + 'ConfirmedHot', sum(1 for r in conf if r['per_call'] == 'yes'), adj)
    else:
        MISSING.append(pre + 'Adjudicated')


# --- drift over a run: passively cooled host (thermal throttling) ------------
# Throttling lowers the clock under sustained load, so it would show as timings
# that rise with run order. Compared: the first and last third of each run.
mech_csv = RUNS / '2026-09-17T08-42-17Z-keypath-mechanism' / 'keypath_mechanism.csv'
if mech_csv.exists():
    g = pd.read_csv(mech_csv)
    g = g[g.condition == 'jwt_hs_string'].sort_values('invocation')
    k = len(g) // 3
    put('DriftHostProcs', len(g), mech_csv)
    put('DriftHostFirst', float(g.median_us.iloc[:k].median()), mech_csv)
    put('DriftHostLast', float(g.median_us.iloc[-k:].median()), mech_csv)
else:
    MISSING.append('DriftHost')
for mode, pre in (('jwt', 'DriftAbJwt'), ('none', 'DriftAbNone')):
    f = RUNS / f'INSITU-AB-authmode-{mode}' / 'pod_cpu_samples.csv'
    if not f.exists():
        MISSING.append(pre); continue
    s = pd.read_csv(f, comment='#')
    s = s[s.container == 'service-a'].sort_values('t_unix')
    k = len(s) // 3
    put(pre + 'First', float(s.cpu_millicores.iloc[:k].median()), f, '{:.1f}')
    put(pre + 'Last', float(s.cpu_millicores.iloc[-k:].median()), f, '{:.1f}')
sweep = RUNS / '2026-09-14T05-57-22Z-verifyrate-hs256' / 'verify_rate_curve.csv'
if sweep.exists():
    v = pd.read_csv(sweep).pivot(index='rate_rps', columns='pass', values='verify_mean_us')
    pct = (v['desc'] / v['asc'] - 1) * 100
    put('DriftSweepRates', len(pct), sweep)
    put('DriftSweepSlowerRates', int((pct > 0).sum()), sweep)
    put('DriftSweepMedianPct', float(pct.median()), sweep, '{:.1f}')
    put('DriftSweepMaxPct', float(pct.max()), sweep, '{:.1f}')
else:
    MISSING.append('DriftSweep')


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(ROOT / 'macros' / 'review_macros.tex'))
    ap.add_argument('--map', default=None)
    a = ap.parse_args(argv)
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    lines = ['% review_macros.tex -- GENERATED. Do not edit.',
             '% Regenerate: python3 -m analysis.make_review_macros',
             '% Every value below is read from a file under data/runs/ or survey/.',
             r'\providecommand{\PLACEHOLDER}[1]{\textcolor{red}{\textbf{[MISSING: #1]}}}', '']
    for k in sorted(NUM):
        lines.append(f'\\newcommand{{\\{k}}}{{{NUM[k]}}}% {SRC[k]}')
    for k in sorted(set(MISSING) - set(NUM)):
        lines.append(f'\\providecommand{{\\{k}}}{{\\PLACEHOLDER{{{k}}}}}')
    out.write_text('\n'.join(lines) + '\n')
    if a.map:
        with open(a.map, 'w', newline='') as f:
            w = csv.writer(f); w.writerow(['macro', 'value', 'source'])
            for k in sorted(NUM):
                w.writerow([k, NUM[k], SRC[k]])
    print(f'wrote {out}: {len(NUM)} values, {len(set(MISSING) - set(NUM))} missing')
    if MISSING:
        print('missing:', ' '.join(sorted(set(MISSING) - set(NUM))), file=sys.stderr)


if __name__ == '__main__':
    main()
