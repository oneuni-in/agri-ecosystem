# Secrets & key handling (SPEC D04-F)

The rule: **the repo carries only SOPS-encrypted secrets; the age private key
exists in exactly two places — the offline copy you control, and (briefly) a
GitHub Actions secret used at deploy time.** Nothing plaintext in git, in
workflow files, or in CI logs.

## One-time setup (human, offline)

1. Generate the keypair on a trusted machine, **not** inside the repo:

   ```sh
   age-keygen -o agri-staging.agekey
   # Public key: age1...   <- printed to stdout
   ```

2. Store `agri-staging.agekey` offline (password manager / encrypted drive).
   It never gets committed, emailed, or copied to the VPS permanently.

3. Put the **public** key into [.sops.yaml](../../.sops.yaml), replacing the
   `age1qqq...` placeholder. The public key is not a secret; committing it is
   the point.

4. Add the **private** key as the GitHub Actions secret `SOPS_AGE_KEY`
   (Settings → Environments → `staging` → secrets, so it is only exposed to
   approved deploy runs — never as a plain repo secret).

## Encrypting staging secrets

```sh
cp secrets/staging.env.example secrets/staging.env   # fill real values
sops --encrypt secrets/staging.env > secrets/staging.sops.env
rm secrets/staging.env                               # plaintext never committed
git add secrets/staging.sops.env
```

`.gitignore` blocks everything under `secrets/` except `*.sops.env` and the
example template, so an accidental `git add secrets/staging.env` is inert.
The `security` CI job (gitleaks, full history) is the backstop.

## How the deploy uses the key

`deploy-staging.yml` pipes `SOPS_AGE_KEY` over SSH stdin into
`~/.config/sops/age/ci-key.txt` on the VPS (mode 600), runs
`scripts/deploy/staging_deploy.sh` which decrypts `secrets/staging.sops.env`
→ `secrets/staging.env` for `docker compose up`, then **deletes both** the
decrypted file (script trap) and the key file (workflow `always()` step).

## Rotation / compromise

1. Generate a new keypair (step 1 above).
2. Replace the recipient in `.sops.yaml`, re-encrypt:
   `sops updatekeys secrets/staging.sops.env` (or decrypt with the old key +
   re-encrypt with the new one).
3. Rotate the *values* too if the old key may have leaked — a stolen key
   decrypts every historical version of the file in git history.
4. Update the `SOPS_AGE_KEY` environment secret; destroy old offline copies.

## What lives where

| Secret | Location | Notes |
| --- | --- | --- |
| age private key | offline + `staging` environment secret `SOPS_AGE_KEY` | never on VPS disk outside a deploy |
| age public key | `.sops.yaml` (committed) | not a secret |
| staging service credentials | `secrets/staging.sops.env` (committed, encrypted) | template: `secrets/staging.env.example` |
| VPS SSH deploy key | `staging` environment secrets `STAGING_SSH_KEY` / `STAGING_HOST` / `STAGING_USER` / `STAGING_KNOWN_HOSTS` | deploy-scoped user, see staging-deploy runbook |
| CI-only creds (`app:app` postgres etc.) | workflow files, in the clear | deliberately throwaway, never reused anywhere |
