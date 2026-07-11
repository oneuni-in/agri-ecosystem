# Runbook: RS256 signing-key rotation (id.agri.in JWKS)

Access tokens are RS256 JWTs signed by one **active** private key; verifiers
resolve the public key from `GET /.well-known/jwks.json` by the token's `kid`
header. Rotation is safe as long as every kid that can still appear in a live
token stays published in JWKS for the overlap window.

**Overlap window = access-token TTL (15 min) + JWKS cache (`max-age=300`, 5
min) = 20 minutes.** Anything longer is fine; shorter strands valid tokens.

Environment knobs (`backend/core/settings.py`):

| env var | meaning |
|---|---|
| `OAUTH_JWT_PRIVATE_KEY_PEM` | active private key (PEM; `\n` escapes accepted in one-line env files) |
| `OAUTH_JWT_KID` | kid stamped into token headers and the JWKS entry |
| `OAUTH_JWT_EXTRA_PUBLIC_KEYS_PEM` | concatenated PUBLIC-key PEMs also published in JWKS (retired/incoming keys); kids are RFC 7638 thumbprints |

Dev/test with no `OAUTH_JWT_PRIVATE_KEY_PEM` generate an ephemeral keypair per
process. **Prod refuses to boot without one** (`OAuthKeyConfigError`).

## Routine rotation

1. **Generate** the new keypair (never reuse a kid):

   ```bash
   openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out new-key.pem
   openssl pkey -in new-key.pem -pubout -out old-key-public.pem   # run against the OLD key
   ```

2. **Deploy overlap**: keep serving the old public key while switching signing
   to the new key —
   - `OAUTH_JWT_PRIVATE_KEY_PEM` = new private key
   - `OAUTH_JWT_KID` = new kid (e.g. `prod-2026-08`)
   - `OAUTH_JWT_EXTRA_PUBLIC_KEYS_PEM` = OLD public key PEM
   - restart the API.

3. **Verify** immediately:

   ```bash
   curl -s https://id.agri.in/.well-known/jwks.json | python -m json.tool
   ```

   Expect BOTH kids, every entry `"use": "sig", "alg": "RS256"`, and no
   private members (`d`, `p`, `q`, `dp`, `dq`, `qi`) anywhere. New tokens from
   `POST /token` must carry the new kid in their header.

4. **Retire** after ≥ 20 minutes: clear `OAUTH_JWT_EXTRA_PUBLIC_KEYS_PEM`,
   restart, re-verify JWKS shows only the active kid. Shred the old private
   key; it is never needed again.

## Emergency rotation (suspected private-key compromise)

Same steps, but **skip the overlap**: do NOT publish the old public key —
every outstanding token dies with the key, which is the point. Expect up to 15
minutes of failed API calls from holders of old tokens; sessions re-mint
tokens on the next refresh (D09). Treat as an incident: record when the key
was rotated and audit token issuance around the suspected window.

## Threat notes

- The private key exists only in the environment; nothing in the repo, image,
  or database ever holds it (gate: `test_jwks_serves_valid_public_keys`
  asserts no private members leave the API).
- Token forgery requires the private key - JWKS itself is public by design.
- Verifiers must select keys by `kid`, never "first key in the set".
