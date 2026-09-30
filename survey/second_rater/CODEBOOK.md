# Codebook: what is passed as the key to `jsonwebtoken.verify()`?

For each row, open the file at the URL given (the exact commit examined) and find
the `verify` call on the line shown or, if none is shown, the call that uses the
binding of the `jsonwebtoken` import. Classify **the second argument** of that
call. Follow the value as far as you can **within the repository**, not only
within the file.

| Label | Use when the second argument is... |
|---|---|
| `keyobject` | a `KeyObject`: built with `crypto.createSecretKey`, `createPublicKey` or `createPrivateKey`, or `KeyObject.from`, anywhere before the call |
| `env_string` | a string read from `process.env` (directly or through config) |
| `string_literal` | a string literal in source code |
| `file_contents` | the contents of a file (`fs.readFileSync` and similar), as a string or Buffer |
| `buffer` | a `Buffer` built from something other than a file |
| `callback` | a function (for example a JWKS `getKey` callback) |
| `other_string` | a string whose origin is known but is none of the above |
| `unresolvable` | you cannot determine what it is, even after reading other files |
| `not_a_verify_call` | the row does not point to a `jsonwebtoken` verify call |

Rules:
1. Rate independently. Do not look at `callsites.csv`, `hand_adjudication.csv`
   or the other rater's column until both columns are complete.
2. Record one label per row in your own column (`rater_1` or `rater_2`), and a
   free-text reason in the matching `notes_` column when the label is
   `unresolvable`, `other_string` or `not_a_verify_call`.
3. Disagreements are resolved afterwards by discussion between the two raters,
   recorded in a `resolved` column with a one-line reason. The agreement
   statistic is computed on the independent labels, **before** resolution.
