/**
 * keypath-equivalence.js -- does the narrow fix change observable behaviour?
 * (reviewer comment M7, second part; reviewer question 3)
 *
 * For every combination of configured key material and token below, run
 * verify() through the stock library and through the narrow ('safe') build and
 * compare the outcome: accepted with the same payload, or rejected with the
 * same error class and message. Any difference is printed and the process
 * exits non-zero. Nothing is timed.
 *
 * The key-material cases include the misconfigurations a reviewer asked about:
 * a PEM public key, a PEM private key and a JWK string supplied where an HMAC
 * secret is expected.
 *
 * Usage:  node bench/keypath-equivalence.js [--out results.csv]
 */
'use strict';
const crypto = require('node:crypto');
const fs = require('node:fs');
const patch = require('./keypath-patch.js');

const outArg = process.argv.indexOf('--out');
const OUT = outArg > 0 ? process.argv[outArg + 1] : null;

const stock = require(patch.PKG);
const safe = require(patch.build('safe'));
const keyonly = require(patch.build('keyonly'));

const SECRET = 'your-super-secret-key-that-is-long';
const rsa = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
const ec = crypto.generateKeyPairSync('ec', { namedCurve: 'P-256' });
const RSA_PUB_PEM = rsa.publicKey.export({ type: 'spki', format: 'pem' });
const RSA_PRIV_PEM = rsa.privateKey.export({ type: 'pkcs8', format: 'pem' });
const EC_PUB_PEM = ec.publicKey.export({ type: 'spki', format: 'pem' });
const RSA_PUB_JWK = JSON.stringify(rsa.publicKey.export({ format: 'jwk' }));

const KEYS = {
  'string secret': SECRET,
  'string secret with leading space': ' ' + SECRET,
  'Buffer secret': Buffer.from(SECRET),
  'KeyObject secret': crypto.createSecretKey(Buffer.from(SECRET)),
  'PEM RSA public key as string': RSA_PUB_PEM,
  'PEM RSA private key as string': RSA_PRIV_PEM,
  'PEM EC public key as string': EC_PUB_PEM,
  'JWK RSA public key as string': RSA_PUB_JWK,
  'empty string': '',
  'PEM RSA public key with leading newline': '\n  ' + RSA_PUB_PEM,
  'PEM RSA public key as Buffer': Buffer.from(RSA_PUB_PEM),
  'JSON text that is not a JWK': '{"k":"not-a-jwk"}',
  'string containing -----BEGIN mid-way': 'secret-----BEGIN-not-pem',
};

const claims = { sub: 'user0' };
const b64u = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
const hmacToken = (key) => {
  const h = b64u({ alg: 'HS256', typ: 'JWT' });
  const p = b64u({ ...claims, iat: 1700000000 });
  const sig = crypto.createHmac('sha256', key).update(`${h}.${p}`).digest('base64url');
  return `${h}.${p}.${sig}`;
};
const TOKENS = {
  'HS256 signed with the secret': stock.sign(claims, SECRET, { algorithm: 'HS256', noTimestamp: true }),
  'HS256 HMACed with the RSA public PEM text': hmacToken(RSA_PUB_PEM),
  'HS256 HMACed with the JWK text': hmacToken(RSA_PUB_JWK),
  'RS256 signed with the RSA private key': stock.sign(claims, rsa.privateKey, { algorithm: 'RS256', noTimestamp: true }),
  'RS256 forged (random signature)': `${b64u({ alg: 'RS256', typ: 'JWT' })}.${b64u(claims)}.${crypto.randomBytes(32).toString('base64url')}`,
  'HS256 forged (random signature)': `${b64u({ alg: 'HS256', typ: 'JWT' })}.${b64u(claims)}.${crypto.randomBytes(32).toString('base64url')}`,
  'alg none': `${b64u({ alg: 'none', typ: 'JWT' })}.${b64u(claims)}.`,
};
const OPTIONS = {
  'no algorithms option': {},
  'algorithms [HS256]': { algorithms: ['HS256'] },
  'algorithms [RS256]': { algorithms: ['RS256'] },
  'algorithms [HS256, RS256]': { algorithms: ['HS256', 'RS256'] },
};

function run(lib, token, key, opts) {
  try {
    const out = lib.verify(token, key, opts);
    return `accepted ${JSON.stringify(out)}`;
  } catch (e) {
    return `rejected ${e.name}: ${e.message}`;
  }
}

let cases = 0, diffs = 0;
const rows = ['key_material,token,options,stock,narrow_fix,identical,keyonly,identical_keyonly'];
let diffsKeyonly = 0;
for (const [kn, key] of Object.entries(KEYS)) {
  for (const [tn, token] of Object.entries(TOKENS)) {
    for (const [on, opts] of Object.entries(OPTIONS)) {
      cases += 1;
      const a = run(stock, token, key, opts);
      const b = run(safe, token, key, opts);
      const k = run(keyonly, token, key, opts);
      const same = a === b;
      const sameK = a === k;
      if (!same) { diffs += 1; console.log(`DIFFERENT (safe): [${kn}] [${tn}] [${on}]\n  stock: ${a}\n  safe:  ${b}`); }
      if (!sameK) { diffsKeyonly += 1; console.log(`DIFFERENT (keyonly): [${kn}] [${tn}] [${on}]\n  stock:   ${a}\n  keyonly: ${k}`); }
      const q = (s) => `"${s.replace(/"/g, '""')}"`;
      rows.push([q(kn), q(tn), q(on), q(a), q(b), same, q(k), sameK].join(','));
    }
  }
}
if (OUT) fs.writeFileSync(OUT, rows.join('\n') + '\n');
console.log(`node ${process.version} openssl ${process.versions.openssl}: ${cases} cases, ${diffs} differ (narrow fix), ${diffsKeyonly} differ (key-material-only)`);
process.exit(diffs === 0 && diffsKeyonly === 0 ? 0 : 1);
