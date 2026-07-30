# Staging deploy runbook (SPEC D04-D/E)

Flow: merge to `dev` → `deploy-staging.yml` **automatically** builds + pushes
all six images to GHCR (`agri-api`, `agri-web-{milk,organic,agri,id,admin}`,
tagged `<sha>` and `dev`) → the `deploy` job **waits for manual approval**
(the `staging` environment) → SSH to the VPS → `scripts/deploy/staging_deploy.sh`
pulls the sha, `docker compose -p agri-staging` up, smoke-tests
`/health/deep` + one page per app, and **auto-rolls back** to the last-good
sha if smoke fails. There is no auto-deploy and no prod yet.

## One-time setup

### On the VPS

1. Create a deploy-scoped user (no sudo): `adduser deploy && usermod -aG docker deploy`.
2. Clone the repo: `sudo -u deploy git clone https://github.com/oneuni-in/agri-ecosystem.git /home/deploy/agri-ecosystem`.
3. Install `sops` (and nothing else — docker + git + curl already exist on the hardened box).
4. Generate a dedicated SSH keypair for CI (`ssh-keygen -t ed25519 -C agri-ci-deploy`),
   add the public half to `/home/deploy/.ssh/authorized_keys`. Restrict it:
   `from="<GitHub Actions egress or your allowlist>"` prefix in authorized_keys,
   per the threat model (deploy-key theft → deploy-scoped, IP-restricted).
5. Log in to GHCR once so pulls work: `docker login ghcr.io` with a read-only
   PAT (`read:packages`).

### On GitHub (Settings → Environments → new environment `staging`)

1. **Required reviewers**: add yourself. This is the manual-approval gate —
   without it the deploy job would run unattended.
2. Environment secrets:
   - `STAGING_HOST` — VPS IP/hostname
   - `STAGING_USER` — `deploy`
   - `STAGING_SSH_KEY` — the private half of the CI keypair (step 4 above)
   - `STAGING_KNOWN_HOSTS` — output of `ssh-keyscan -H <host>` (pins the host key)
   - `SOPS_AGE_KEY` — the age private key (see [secrets.md](secrets.md))

### Secrets file

Follow [secrets.md](secrets.md) to commit `secrets/staging.sops.env`. The
deploy fails loudly at the decrypt step until this exists with real values.

### Repository variables (Settings → Secrets and variables → Actions → Variables tab)

- `NEXT_PUBLIC_CONSOLE_URL` — the Business Console's public origin (the
  web-agri app, e.g. its `agri.in` host). `deploy-staging.yml`'s
  `build-push` job passes this as the `CONSOLE_URL` build-arg to
  `apps/Dockerfile` when building the `web-milk` image (Task 11 fix round
  2). It is a plain repo **variable**, not a secret — a hostname isn't
  sensitive, and secrets get masked in Action logs, which would make a
  misconfigured value harder to diagnose.
  - This is a `NEXT_PUBLIC_` var: Next.js inlines it into the JS bundle at
    build time. There is no runtime knob for it — changing the value
    requires rebuilding and redeploying the `web-milk` image, not just
    restarting the container.
  - If this variable is unset, the `web-milk` image build **fails on
    purpose** (`apps/web-milk/lib/console.ts` throws a
    `NEXT_PUBLIC_CONSOLE_URL is not set` error at build time) rather than
    silently shipping a dead cross-origin "List your dairy business" link
    to real visitors. Set the variable and re-run the `build-push` job (or
    re-push to `dev`) to clear the failure.

## Running a deploy

1. Merge a PR into `dev` (or run `deploy-staging` via *Actions → Run workflow*).
2. Wait for the six `build-push` matrix jobs to go green.
3. Approve the `deploy` job when GitHub asks for environment review.
4. Watch the job log: each smoke URL prints `smoke OK`. On success the VPS
   records the sha in `.staging-deployed` (the rollback anchor for next time).

Staging ports on the VPS: API `:8100`, apps `:3100`–`:3104`
(milk, organic, agri, id, admin).

After the first successful deploy, activate monitoring + backups:
docs/runbooks/monitoring.md and docs/runbooks/backup-restore.md
("ACTIVATE AT LAUNCH PREP" sections).

## When smoke fails

The script re-deploys the previous last-good sha automatically and exits
non-zero (job shows red). If the log ends with `ROLLBACK ALSO FAILED`, SSH in
and debug: `docker compose -p agri-staging -f docker-compose.staging.yml ps`
/ `logs api`. The decrypted `secrets/staging.env` is deleted on every exit —
re-run the deploy script rather than hand-editing env on the box.

## Manual deploy / rollback from the VPS

```sh
cd ~/agri-ecosystem && git fetch origin dev && git reset --hard origin/dev
SOPS_AGE_KEY_FILE=<path-to-key> bash scripts/deploy/staging_deploy.sh <sha>
```

Roll back by passing the older sha explicitly.
