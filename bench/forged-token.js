/**
 * forged-token.js -- what does a REJECTED token cost? (reviewer comment M7)
 *
 * Same protocol and output format as keypath-mechanism.js: exactly one
 * condition per process, --iterations timed calls after --warmup, one CSV row
 * per process, the process's own versions recorded on the row.
 *
 * The service is configured with an ordinary HMAC shared secret. The client
 * does not know it. Every token below is well formed (three segments, JSON
 * header and payload, non-empty signature) and every one is rejected.
 *
 *   forged_rs_string          stock library, string secret, token declares RS256
 *   forged_rs_string_safe     narrow fix,    string secret, token declares RS256
 *   forged_rs_preparsed       stock library, KeyObject secret, token declares RS256
 *   forged_hs_string          stock library, string secret, token declares HS256, bad signature
 *   forged_hs_string_safe     narrow fix,    string secret, token declares HS256, bad signature
 *   forged_hs_preparsed       stock library, KeyObject secret, HS256, bad signature
 *   probe_throws_s16          createPublicKey() on a 16-character secret (fails)
 *   probe_throws_s256         createPublicKey() on a 256-character secret (fails)
 *
 * The HMAC secret is the one keypath-mechanism.js uses (34 characters); the two
 * probe_throws_s* conditions vary only its length (reviewer minor 15).
 *
 * Usage:
 *   node bench/forged-token.js --condition forged_rs_string \
 *        --iterations 20000 --warmup 10000 --invocation 1 --environment host --out run.csv
 */
'use strict';
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const patch = require('./keypath-patch.js');

const args = { iterations: 20000, warmup: 10000, invocation: 0, out: null, condition: null,
               environment: 'host' };
for (let i = 2; i < process.argv.length; i += 2) {
  const k = process.argv[i].replace(/^--/, '');
  if (!(k in args)) { console.error(`unknown argument: ${process.argv[i]}`); process.exit(2); }
  args[k] = /^(iterations|warmup|invocation)$/.test(k) ? Number(process.argv[i + 1]) : process.argv[i + 1];
}
if (!args.condition) { console.error('--condition is required'); process.exit(2); }

// --- fixtures, built outside every timing loop -------------------------------
const jwtStock = require(patch.PKG);
const HMAC_SECRET = 'your-super-secret-key-that-is-long';
const HMAC_KEYOBJECT = crypto.createSecretKey(Buffer.from(HMAC_SECRET));
const SECRET_16 = 'a'.repeat(16);
const SECRET_256 = 'a'.repeat(256);
const CLAIMS = { sub: 'user0', name: 'Load User 0', exp: 4102444800 };

const b64u = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
// A signature of plausible length that nobody holding the secret produced.
const FAKE_SIG = crypto.createHash('sha256').update('not-signed-by-the-secret').digest('base64url');
const FORGED_RS = `${b64u({ alg: 'RS256', typ: 'JWT' })}.${b64u(CLAIMS)}.${FAKE_SIG}`;
const FORGED_HS = `${b64u({ alg: 'HS256', typ: 'JWT' })}.${b64u(CLAIMS)}.${FAKE_SIG}`;

let jwtSafe = null;
const safeLib = () => (jwtSafe || (jwtSafe = require(patch.build('safe'))));

// verify() throws on rejection; the error is caught and discarded, as a
// request handler would, and its message is checked once below.
const reject = (lib, token, key) => () => {
  try { lib.verify(token, key, { algorithms: ['HS256'] }); return 'accepted'; }
  catch (e) { return e.message; }
};

const CONDITIONS = {
  forged_rs_string:      () => reject(jwtStock, FORGED_RS, HMAC_SECRET),
  forged_rs_string_safe: () => reject(safeLib(), FORGED_RS, HMAC_SECRET),
  forged_rs_preparsed:   () => reject(jwtStock, FORGED_RS, HMAC_KEYOBJECT),
  forged_hs_string:      () => reject(jwtStock, FORGED_HS, HMAC_SECRET),
  forged_hs_string_safe: () => reject(safeLib(), FORGED_HS, HMAC_SECRET),
  forged_hs_preparsed:   () => reject(jwtStock, FORGED_HS, HMAC_KEYOBJECT),
  probe_throws_s16:      () => () => { try { crypto.createPublicKey(SECRET_16); } catch (_) { return 0; } return 1; },
  probe_throws_s256:     () => () => { try { crypto.createPublicKey(SECRET_256); } catch (_) { return 0; } return 1; },
};

const make = CONDITIONS[args.condition];
if (!make) { console.error(`unknown condition: ${args.condition}`); process.exit(2); }
const fn = make();

// Every forged condition must actually be rejected, and for the reason stated.
const outcome = fn();
if (outcome === 'accepted' || outcome === 1) {
  console.error(`${args.condition}: token was ACCEPTED or probe succeeded; refusing to time it`);
  process.exit(3);
}

// --- measure -----------------------------------------------------------------
for (let i = 0; i < args.warmup; i += 1) fn();

const samples = new Float64Array(args.iterations);
for (let i = 0; i < args.iterations; i += 1) {
  const t0 = process.hrtime.bigint();
  fn();
  samples[i] = Number(process.hrtime.bigint() - t0) / 1000;
}

let overhead = 0;
{
  const n = 20000, s = new Float64Array(n);
  for (let i = 0; i < n; i += 1) {
    const t0 = process.hrtime.bigint();
    s[i] = Number(process.hrtime.bigint() - t0) / 1000;
  }
  overhead = Array.from(s).sort((a, b) => a - b)[n >> 1];
}

const sorted = Array.from(samples).sort((a, b) => a - b);
const n = sorted.length;
const mean = sorted.reduce((p, c) => p + c, 0) / n;
const sd = Math.sqrt(sorted.reduce((p, c) => p + (c - mean) ** 2, 0) / (n - 1));
const q = (p) => sorted[Math.min(n - 1, Math.floor(n * p))];

const row = {
  environment: args.environment,
  condition: args.condition,
  invocation: args.invocation,
  n,
  mean_us: mean.toFixed(4),
  median_us: q(0.5).toFixed(4),
  p90_us: q(0.9).toFixed(4),
  p99_us: q(0.99).toFixed(4),
  min_us: sorted[0].toFixed(4),
  max_us: sorted[n - 1].toFixed(4),
  stddev_us: sd.toFixed(4),
  timer_overhead_us: overhead.toFixed(4),
  node_version: process.version,
  openssl_version: process.versions.openssl,
  v8_version: process.versions.v8,
  platform: `${process.platform}/${process.arch}`,
  rejection: String(outcome).replace(/[,\n]/g, ' '),
};

const header = Object.keys(row).join(',');
const line = Object.values(row).join(',');
if (args.out) {
  const exists = fs.existsSync(args.out);
  fs.mkdirSync(path.dirname(args.out), { recursive: true });
  fs.appendFileSync(args.out, (exists ? '' : header + '\n') + line + '\n');
}
console.log(header);
console.log(line);
