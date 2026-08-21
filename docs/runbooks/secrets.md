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
cp secrets/staging.env.example secrets/staging.sops.env   # fill real values
sops --encrypt --in-place secrets/staging.sops.env        # encrypts where it sits
git add secrets/staging.sops.env
```

**Name the file `*.sops.env` BEFORE encrypting, and encrypt in place.** The
obvious shape - `sops --encrypt secrets/staging.env > secrets/staging.sops.env`
- fails with:

```
error loading config: no matching creation rules found
```

which reads like a broken key and is not. sops picks its creation rule from
the path of the file it is READING, and `secrets/staging.env` does not contain
`.sops.`, so no rule matches and it never gets as far as the recipient.
Encrypting in place means the name matches from the start.

There is no separate plaintext file to delete afterwards: `--in-place`
rewrites the same file, so the window where a filled-in plaintext copy exists
on disk is as short as it can be. If you do keep an intermediate copy, delete
it - `.gitignore` blocks everything under `secrets/` except `*.sops.env` and
the template, so an accidental `git add secrets/staging.env` is inert, but
inert-in-git is not the same as gone-from-disk.

`*.agekey` and `*.age.key` are ignored repo-wide, not just under `secrets/`,
so a private key that lands anywhere in the tree cannot be staged. The
`security` CI job (gitleaks, full history) is the backstop for content that
did get committed - but it runs after the push, by which point a leaked key
has to be treated as burned. The ignore rules are what stop it earlier.

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
