# D14 Sprint-1 Hardening + Gate 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close Sprint 1 with zero Critical/High findings, a verified-committed migration/grant/event/header/proxy surface, the deferred D13 items explicitly resolved (fix-now or documented defer), backend-storm promoted to a required CI check, and Gate 2 recorded — then promote `dev` → `main` as `v0.2.0`.

**Architecture:** No new features or subsystems. This is an audit-fix-verify-gate-promote pass over the existing D06–D13 surface (identity, coins, audit, notify, RBAC, BFF proxies, header). Work happens on `feat/d14-sprint1-hardening` (already checked out, branched off `dev`).

**Tech Stack:** FastAPI + SQLAlchemy/Alembic (Python 3.13) backend; Next.js 15 App Router BFFs (TypeScript); Postgres 16 + Redis 7; pytest (backend), Playwright (e2e); GitHub Actions CI.

## Global Constraints

- Endpoints are private, rate-limited, and validated unless explicitly `public=True` (and then declared in `backend/core/public_routes.txt` in the same PR).
- All list endpoints are cursor-paginated; all IDs are UUIDv7; user content defaults to `pending`.
- Boring, reversible, measured choices. No net-new features. No refactors beyond what a task strictly requires.
- `modules.identity` and `modules.coins` never import each other — cross-module effects go through `shared/events.py` (Redis Streams) only (both modules' `CLAUDE.md`).
- Never log request bodies, query strings, or raw exception messages in `identity`/`coins` — PII/token material risk (both modules' `CLAUDE.md`, `shared/telemetry.py` PiiScrubFilter is last-line, not a license).
- Tokens never reach the browser — BFF routes attach `Authorization` server-side only (D10 non-negotiable, restated in every `[...path]/route.ts` file header).
- UI matches `docs/design-system.md`; tokens only, no raw hex in app code (not touched by this plan — no UI visual changes).
- `main` and `dev` are protected: **never commit directly**; every task's commits land on `feat/d14-sprint1-hardening` (or a dedicated tiny chore branch for Task 1) and reach `dev` only via PR.
- Conventional commits required (enforced by CI's `conventional-commits` job and PR title).
- `gh` CLI is **not installed** in this environment — every step that would use `gh pr create` / `gh api` instead produces the exact command for the human to run, or a GitHub compare-URL, and pauses for a human checkpoint. Flag this clearly at each such step; do not attempt to fake it.

---

## Pre-flight state (already confirmed by recon — do not re-discover)

- Current branch: `feat/d14-sprint1-hardening`, off `dev`, clean except an **unrelated pre-existing** local modification to `.claude/settings.json` (session tool-permission grants accumulated by this Claude Code session; not part of the D14 spec — leave it alone, it is not a D13/dev artifact and not in AM state).
- `dev` is 1 local commit ahead of `origin/dev`: `8afc805 "day 13"` (touches `.claude/settings.json` + 4 `apps/web-id` files — harness settings + web-id localhost→127.0.0.1). `origin/dev` has nothing local `dev` lacks.
- `dev-backup-pre-sync` branch exists locally only (not pushed) — keep until `v0.2.0` tags per spec.
- Migration chain (`backend/core/alembic/versions/0001`–`0015`) is **verified clean already**: linear, no duplicates, no orphans, filename↔revision match, working tree == committed HEAD. No fix needed for A1 — Task 4 documents this as evidence.
- Grant matrix (A2) is **already correct on this branch**: `0015_coins_harden_app_rt.py` already revokes UPDATE/DELETE on `coins.ledger_entries` from `app_rt`; `audit.entries` never had UPDATE/DELETE granted to `app_rt`. Both `coins-worker` and `notify-worker` already connect as `app_rt` (`docker-compose.dev.yml:43`, `shared/db.py:122`). No service found connecting as `app` at runtime. No fix needed for A2 — Task 4 documents this as evidence; only staging (`secrets/staging.env`, not in repo) is unverifiable from committed files and must be noted as an assumption.
- AuthCluster (A4) already renders **exactly one** coins pill per header across all 4 apps (the pill lives outside `AuthCluster` itself, as a sibling in each app's `site-header.tsx`). Only the "document as the integration point" comment is missing — Task 7 adds it.
- A5 (BFF path-traversal) is a **real, unfixed gap**: `new URL()` silently collapses `..` segments during parsing, which can strip the `/coins`, `/admin`, or `/notify` prefix a proxy is meant to enforce "by construction" — the comment's claim is not actually enforced by any code. Task 6 fixes this.
- A3 (event-stream contract) found two brittle exact-count test assertions (`test_session_router.py:209,240`) but no actual bug — documented as a Low note in Task 4, not fixed (changing test assertion style is unrelated churn outside this spec's scope; flagging it is the ask).

---

### Task 1: P0 — extract the stray `dev` commit onto its own chore branch and resync `dev`

**Files:**
- No new files. Git branch/ref operations only.

**Interfaces:** N/A (git workflow task).

- [ ] **Step 1: Create the chore branch at current `dev` (carries the stray commit)**

```bash
git checkout dev
git checkout -b chore/dev-harness-sync
git push -u origin chore/dev-harness-sync
```

- [ ] **Step 2: Open the PR (human checkpoint — `gh` CLI is not installed here)**

Print this for the user and stop for confirmation before continuing:

```
gh is not available in this environment. Please open a PR manually:
  https://github.com/oneuni-in/agri-ecosystem/compare/dev...chore/dev-harness-sync?expand=1
Title: chore: sync harness settings + web-id localhost -> 127.0.0.1
Body: Carries the local-only commit 8afc805 ("day 13") that landed directly
on dev, in violation of the branch-protection convention. No functional
change beyond what 8afc805 already contains.
```

Wait for the user to confirm the PR is merged into `dev` before Step 3.

- [ ] **Step 3: Resync local `dev` to match `origin/dev` (confirm with the user before running — this rewrites the local `dev` branch pointer)**

```bash
git fetch origin
git log origin/dev..dev   # sanity check: should now be empty once the PR above is merged
git checkout dev
git reset --hard origin/dev
```

Safety: `dev-backup-pre-sync` (local) and `chore/dev-harness-sync` (pushed, merged) both already hold the commit's content, so this reset cannot lose it. **Do not run Step 3 until the user has confirmed the PR merged.**

- [ ] **Step 4: Return to work**

```bash
git checkout feat/d14-sprint1-hardening
git status   # confirm clean except the pre-existing .claude/settings.json note above
```

---

### Task 2: P1 — document `backend-storm` as the 9th required check (owner action handoff)

**Files:**
- Modify: `docs/runbooks/branch-protection.md`

**Interfaces:** N/A (docs + human handoff).

- [ ] **Step 1: Update the required-checks list**

In `docs/runbooks/branch-protection.md`, change the bulleted list (currently 8 items, lines 34-42) to add a 9th entry after `backend`:

```markdown
  - `web`
  - `design-tokens`
  - `backend`
  - `backend-storm`
  - `public-routes`
  - `security`
  - `lighthouse`
  - `e2e-auth`
  - `conventional-commits`
```

Update every "eight" reference in the file to "nine" (the verification-log check-count line, the no-CLI-fallback paragraph, and the checklist item text).

- [ ] **Step 2: Append a verification-log row (matches the file's own D09 convention at line 85)**

```markdown
| 2026-07-14 | dev, main | (pending human: add `backend-storm` to the ruleset's required checks) | D14 adds the 9th required check: `backend-storm` (10k-coins-storm concurrency proof, D13) |
```

- [ ] **Step 3: Print the exact handoff for the user (owner action — `gh` unavailable, and rulesets are non-enforced on the free plan per the file's own "Known Gap" section, so this is metadata-only until a Team upgrade, but must still be added so it activates automatically then)**

```
Owner action needed (GitHub UI, Settings -> Rules -> Rulesets -> "secure
branch rules" -> edit -> Require status checks to pass -> add `backend-storm`)
for BOTH dev and main. This cannot be scripted here (gh CLI not installed).
Non-blocking for this PR's merge today (the ruleset isn't enforced on the
free plan yet per the doc's Known Gap), but must be recorded before v0.2.0
tags per the D14 non-negotiables.
```

- [ ] **Step 4: Commit**

```bash
git add docs/runbooks/branch-protection.md
git commit -m "docs(d14): document backend-storm as the 9th required check"
```

---

### Task 3: P2 — staged-file discipline gate

**Files:**
- Create: `backend/core/scripts/check_fully_staged.py` (repo root staging check — Python, no venv activation needed to run `git diff`)
- Create: `backend/core/tests/test_check_fully_staged.py`

Actually place the script at the repo root's `scripts/` directory (there is already a root-level `scripts/` used by `scripts/check-hex.mjs`, `scripts/capture-baseline.mjs` per `package.json`), not inside `backend/core`, since this check is repo-wide, not backend-specific:

**Files (corrected):**
- Create: `scripts/check_fully_staged.py`
- Create: `scripts/test_check_fully_staged.py` (plain `pytest`-free — this project's root has no Python test runner; write it as a self-contained script with `if __name__ == "__main__"` assertions instead, run manually once, not wired into CI test discovery)

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Fail if any tracked path is staged AND has further unstaged edits (AM
state in `git status --porcelain`). This is the exact failure class from the
D13 near-miss: content edited after `git add`, so the commit held a stale
version while the working tree (and CI) saw something else.

Run before every commit: python scripts/check_fully_staged.py
"""

import subprocess
import sys


def main() -> int:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    bad = [
        line
        for line in result.stdout.splitlines()
        if len(line) >= 2 and line[0] != " " and line[0] != "?" and line[1] != " "
    ]
    if bad:
        print("STAGED-THEN-MODIFIED files found (git add again before committing):")
        for line in bad:
            print(f"  {line}")
        return 1
    print("check_fully_staged: OK — no staged-then-modified files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify it catches the AM case**

```bash
echo "x" >> README.md 2>/dev/null || echo "x" >> docs/superpowers/plans/2026-07-14-d14-sprint1-hardening.md
git add docs/superpowers/plans/2026-07-14-d14-sprint1-hardening.md
echo "y" >> docs/superpowers/plans/2026-07-14-d14-sprint1-hardening.md
python scripts/check_fully_staged.py
```

Expected: prints the `AM ` line for that path and exits 1.

- [ ] **Step 3: Clean up the manual test edit and verify green**

```bash
git checkout -- docs/superpowers/plans/2026-07-14-d14-sprint1-hardening.md
git reset docs/superpowers/plans/2026-07-14-d14-sprint1-hardening.md
python scripts/check_fully_staged.py
```

Expected: exit 0, "OK" message (the plan file itself will actually be untracked/new at this point in the branch's history — that's fine, untracked files are `??` and explicitly excluded from the `bad` filter above).

- [ ] **Step 4: Add the reminder to `CLAUDE.md`'s workflow section is out of scope (spec says "one-line reminder OR a script" — the script satisfies it). Wire it as a manual pre-commit step documented in the PR description, not a git hook (no `.husky`/`pre-commit` tooling exists in this repo and adding one is a bigger change than "cheap insurance" calls for).**

- [ ] **Step 5: Commit**

```bash
git add scripts/check_fully_staged.py
git commit -m "chore(d14): add staged-file discipline check (P2, D13 near-miss guard)"
```

From this commit onward, run `python scripts/check_fully_staged.py` before every subsequent commit in this plan and confirm it prints OK.

---

### Task 4: Write `docs/security/sprint1-audit.md` — record A1-A5 findings already established

**Files:**
- Create: `docs/security/sprint1-audit.md`

- [ ] **Step 1: Write the audit doc skeleton with A1-A5 evidence** (Part A6 findings from Task 5 get appended later in this same file; the deferred-items table from Part B gets appended in Task 11-13)

```markdown
# Sprint 1 adversarial audit (D14, 2026-07-14)

Scope: D06-D13 (identity, coins, audit, notify, RBAC), with explicit focus
on the integration seams no single spec tested. Findings are graded
Critical / High / Medium / Low; the D14 non-negotiable is zero Critical/High
at tag.

## A1. Migration chain integrity (committed tree)

Verified via `git show HEAD:<file>` for every file in
`backend/core/alembic/versions/` (0001-0015): one straight linear chain,
`revision` == the numeric filename prefix for every file, every
`down_revision` resolves to exactly one existing revision, no duplicates,
no orphans. Working tree == committed HEAD for all five 0011-0015 files
(no drift). **No finding — chain is clean.**

Command used (repeatable):
```bash
for f in backend/core/alembic/versions/00{11..15}_*.py; do
  git show "HEAD:$f" > /tmp/committed_$(basename "$f")
  diff -q /tmp/committed_$(basename "$f") "$f" || echo "DRIFT: $f"
done
```

## A2. Role/grant matrix across schemas

`app_rt` grants audited across identity/coins/directory/leads/content/
market/ads/notify/billing/geo/public (blanket loop, `0013_audit_v1.py:99-107`)
plus the two hardened carve-outs:

- `audit.entries`: SELECT+INSERT only for `app_rt`, always (never in the
  blanket loop) — `0013_audit_v1.py:109-113`. Immutable at grant level.
- `coins.ledger_entries`: UPDATE/DELETE revoked from `app` at creation
  (`0012_coins_v1.py:219,221`), re-opened for `app_rt` by the blanket loop
  (`0013_audit_v1.py:101`), re-revoked in `0015_coins_harden_app_rt.py:40`.
  **Current HEAD state: immutable at grant level**, backed by the
  `coins.reject_ledger_mutation` trigger as defense-in-depth
  (`0012_coins_v1.py:201-218`).

Service connections: `api` uses `app_rt` (`docker-compose.dev.yml:10`),
`worker` (coins) uses `app_rt` (`docker-compose.dev.yml:43`), `notify`
worker uses `app_rt` via the same `shared.db.get_sessionmaker`
(`shared/db.py:122`). No service found using `app` for runtime traffic in
the committed dev compose file. `app` is the migration/table-owner role
(`DATABASE_ADMIN_URL`), never a connecting role for app traffic.

**No finding for dev.** Staging (`docker-compose.staging.yml` reads from
`secrets/staging.env`, not in the repo) could not be verified from
committed files — recorded as an open assumption, not a Critical/High
(no evidence of a problem, just no evidence either way).

## A3. Event-stream contract

Events on the `identity` stream and their consumers:

| Event | Emitted | Consumed by |
|---|---|---|
| `user.registered` | `session_router.py:160-169` (new user, login) | `coins/worker.py:38` (signup_complete award + referral attribution) |
| `identity.signup_completed` | `session_router.py:184-188` | `notify/consumers.py` EVENT_ROUTES |
| `identity.login_new_device` | `session_router.py:190-194` | `notify/consumers.py` EVENT_ROUTES |
| `identity.role_changed` | `admin_router.py:254-260` | `notify/consumers.py` EVENT_ROUTES |
| `identity.session_resumed` (new, D14 Task 8) | `session_router.py` `/auth/me` | `coins/worker.py` (daily_visit award) |

Both consumers (`notify/consumers.py` dict-lookup, `coins/worker.py`
if/elif) are **presence-based / tolerant of unknown event types** — an
unexpected event on the stream cannot break consumer logic.

**Low finding (not fixed in D14, flagged only):**
`backend/core/tests/test_session_router.py:209` and `:240` assert exact
`len(entries) == N` on the login flow's published events. These will need
updating the moment a future spec adds another event inside `login()`'s
new-user/new-device branches. `test_identity_user_registered.py:76` uses a
tolerant `.count(...)` pattern instead — that's the safer style for new
tests. Recording this as a Low style note for D15+, not fixing it now (the
counts are currently correct; changing test style is unrelated churn).

`EVENT_STREAM = "identity"` is independently defined (same value) in three
files (`session_router.py:60`, `profile_router.py:52`, `admin_router.py:46`)
— duplication, not a bug; a D13 plan note already flagged consolidating it
as a future nice-to-have.

## A4. Shared header component (AuthCluster)

Confirmed **exactly one** coins pill renders per header, across all 4 apps
(`web-agri`, `web-organic`, `web-milk`, `web-admin` `site-header.tsx`), via
each app's own `<CoinsBalancePill>` placed as a sibling of `<AuthCluster>`
— `AuthCluster` itself (`packages/auth-client/src/react.tsx:81-98`) renders
only the avatar/login-button, no widgets, no dead/commented branches.
**No duplication finding.** Task 7 adds an explicit "this is the
integration point, put siblings not internals" comment so a future spec
doesn't regress this.

## A5. BFF path-traversal

**Medium finding, fixed in Task 6.** All 8 `[...path]` catch-all proxies
(`web-admin/coins,admin`, `web-agri/coins,notify`, `web-milk/coins,notify`,
`web-organic/coins,notify`) build the upstream URL as
`new URL(`${API}/<prefix>/${path.map(encodeURIComponent).join("/")}`)`.
`encodeURIComponent` does not escape `.`, so a raw `..` path segment
survives into the URL string; `new URL()`'s WHATWG dot-segment
normalization then silently collapses it, which can strip the intended
`/coins`, `/admin`, or `/notify` prefix and retarget the request at a
sibling backend prefix on the same host (it cannot escape the origin, only
the intended path prefix). The route header comment's claim ("Only the
backend's /X prefix is reachable through this route by construction") was
not actually enforced by any code. Backend RBAC still gates every route
regardless of which BFF proxy reached it, so this was defense-in-depth
missing, not a full authz bypass — graded Medium, not High, on that basis.
Fixed by rejecting any `.`/`..`/empty path segment up front, before the
auth check, in all 8 files (Task 6).

## A6. Generic attack surface

<!-- Task 5 appends its findings here -->

## Part B deferred-items decisions

<!-- Tasks 11-13 append the decision table here -->
```

- [ ] **Step 2: Commit**

```bash
python scripts/check_fully_staged.py
git add docs/security/sprint1-audit.md
git commit -m "docs(d14): record A1-A5 audit findings (migration chain, grants, events, header, BFF)"
```

---

### Task 5: Part A6 — dispatch the generic adversarial audit sweep

**Files:**
- Modify: `docs/security/sprint1-audit.md` (append the A6 section)

**Process (not literal TDD — this is an audit dispatch task):**

- [ ] **Step 1: Dispatch parallel hostile-auditor agents, one per surface, each told to attack ONLY its area and report findings as `severity | file:line | PoC reasoning | suggested fix`:**
  1. OTP flooding/brute-force/enumeration/race (`modules/identity/otp_service.py`, `otp_router.py` if present, rate-limit config)
  2. OAuth code replay / PKCE downgrade / redirect-URI / state param (`modules/identity` OAuth files, `authlib` usage per D08)
  3. Session rotation races / refresh family-revoke bypass / fixation (`session_service.py`, `refresh_service.py`, `session_router.py`)
  4. RBAC escalation / IDOR on profile + admin endpoints (`modules/identity/admin_router.py`, `profile_router.py`, `require_permission`/`require_auth` usage)
  5. Coins idempotency races / cap bypass / referral farming / negative balance (`modules/coins/service.py`, `rules.py`, `referrals.py`, `admin_router.py`)
  6. Audit chain gaps / notify spam (`shared/audit.py`, `modules/notify/consumers.py`, `scripts/verify_audit_chain.py`)

  Each agent works read-only (no edits) against the current committed tree on `feat/d14-sprint1-hardening`.

- [ ] **Step 2: Consolidate every returned finding into the A6 section of `docs/security/sprint1-audit.md`, one row per finding, in a table: `| Severity | Area | File:line | Description | Status |`. Status starts as `open` for everything.**

- [ ] **Step 3: For each Critical/High finding, adversarially verify it before trusting it** — dispatch a second, independent agent per Critical/High finding whose only job is to try to refute it (reproduce the failure, or show why it doesn't hold given the actual code path, e.g. a check that already exists two lines away). Mark each finding `confirmed` or `refuted` in the table with one line of reasoning. Drop `refuted` rows from the Critical/High fix list (keep them in the doc marked refuted, for the record, not deleted).

- [ ] **Step 4: Commit the consolidated, verified A6 findings**

```bash
python scripts/check_fully_staged.py
git add docs/security/sprint1-audit.md
git commit -m "docs(d14): Part A6 generic audit sweep — OTP/OAuth/sessions/RBAC/coins/audit findings"
```

This task's OUTPUT (the confirmed Critical/High rows) feeds Task 14.

---

### Task 6: Fix A5 — BFF path-traversal hardening across all 8 proxy routes

**Files:**
- Modify: `apps/web-admin/app/api/admin/[...path]/route.ts`
- Modify: `apps/web-admin/app/api/coins/[...path]/route.ts`
- Modify: `apps/web-agri/app/api/coins/[...path]/route.ts`
- Modify: `apps/web-agri/app/api/notify/[...path]/route.ts`
- Modify: `apps/web-milk/app/api/coins/[...path]/route.ts`
- Modify: `apps/web-milk/app/api/notify/[...path]/route.ts`
- Modify: `apps/web-organic/app/api/coins/[...path]/route.ts`
- Modify: `apps/web-organic/app/api/notify/[...path]/route.ts`
- Create: `e2e/bff-path-traversal.spec.ts`

**Interfaces:**
- Every file's `forward()` function gains an early guard, before the `auth.getAccessToken()` call, so the reject is testable without a session.

- [ ] **Step 1: Write the failing e2e test first**

`e2e/bff-path-traversal.spec.ts` (new file; reuses the existing suite's `web-organic` webServer on port 3001 — `web-admin`/`web-agri` are not started by `e2e/playwright.config.ts` today, which is an existing, pre-D14 gap, not something this task expands):

```ts
import { expect, test } from "@playwright/test";

// web-organic is already one of this suite's webServer entries (port 3001);
// its /api/coins and /api/notify proxies share the exact forward() pattern
// being hardened in this change across all 8 catch-all routes.
const ORIGIN = "http://localhost:3001";

const ATTACKS = [
  "/api/coins/%2e%2e/%2e%2e/admin/rules",
  "/api/notify/%2e%2e/%2e%2e/admin/rules",
  "/api/coins/./balance",
];

test.describe("BFF catch-all proxies reject dot-segments (D14 A5)", () => {
  for (const path of ATTACKS) {
    test(`rejects ${path} with 400, never reaches upstream`, async ({ request }) => {
      const res = await request.get(`${ORIGIN}${path}`);
      expect(res.status()).toBe(400);
      const body = await res.json();
      expect(body.detail).toBe("invalid_path");
    });
  }
});
```

- [ ] **Step 2: Run it to verify it fails (server still returns 401 or 200, not 400)**

```bash
pnpm --filter @agri/web-organic dev &
npx playwright test --config e2e/playwright.config.ts e2e/bff-path-traversal.spec.ts
```

Expected: FAIL — current code returns 401 (`unauthenticated`) for the unencoded case or lets the encoded `..` through to `new URL()` collapse, never 400 with `invalid_path`.

- [ ] **Step 3: Apply the identical guard to all 8 files.** Example for `apps/web-agri/app/api/coins/[...path]/route.ts` (same edit shape in all 8 — only the prefix name in the comment/URL differs per file, already correct in each):

```ts
async function forward(
  req: NextRequest,
  params: Promise<{ path: string[] }>,
  method: "GET" | "POST",
): Promise<NextResponse> {
  const { path } = await params;
  if (path.some((segment) => segment === ".." || segment === "." || segment === "")) {
    return NextResponse.json({ detail: "invalid_path" }, { status: 400 });
  }
  const token = await auth.getAccessToken();
  if (!token) return NextResponse.json({ detail: "unauthenticated" }, { status: 401 });
  const url = new URL(`${API}/coins/${path.map(encodeURIComponent).join("/")}`);
  url.search = req.nextUrl.search;
  const upstream = await fetch(url, {
    method,
    headers: {
      authorization: `Bearer ${token}`,
      ...(method === "POST" ? { "content-type": "application/json" } : {}),
    },
    ...(method === "POST" ? { body: await req.text() } : {}),
    cache: "no-store",
  });
  if (upstream.status === 204 || upstream.status === 205 || upstream.status === 304) {
    return new NextResponse(null, { status: upstream.status });
  }
  const body = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
  return NextResponse.json(body, { status: upstream.status });
}
```

Apply the same 4-line insertion (`const { path } = await params;` moved above the token check, plus the `if (path.some(...))` guard) to the other 7 files — each keeps its own `/admin/`, `/coins/`, or `/notify/` prefix and its own method union (`web-admin/admin` has `GET | POST | PUT | DELETE`; the rest have `GET | POST`).

- [ ] **Step 4: Run the e2e test again, confirm it passes**

```bash
npx playwright test --config e2e/playwright.config.ts e2e/bff-path-traversal.spec.ts
```

Expected: PASS, all 3 cases return 400 with `{"detail":"invalid_path"}`.

- [ ] **Step 5: Manual verification against `web-admin`'s admin proxy (not in the e2e webServer list — documented as an existing gap, not expanded today)**

```bash
pnpm --filter @agri/web-admin dev &
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:3004/api/admin/%2e%2e/%2e%2e/coins/rules"
```

(Confirm the actual dev port for web-admin from its `package.json` dev script / `.env` before running.) Expected: `400`. Paste this output into `docs/security/sprint1-audit.md`'s A5 section as manual evidence, and note that `web-admin`/`web-agri` are outside the automated e2e webServer list (pre-existing, out of scope to expand today).

- [ ] **Step 6: Commit**

```bash
python scripts/check_fully_staged.py
git add apps/web-admin/app/api/admin/\[...path\]/route.ts \
        apps/web-admin/app/api/coins/\[...path\]/route.ts \
        apps/web-agri/app/api/coins/\[...path\]/route.ts \
        apps/web-agri/app/api/notify/\[...path\]/route.ts \
        apps/web-milk/app/api/coins/\[...path\]/route.ts \
        apps/web-milk/app/api/notify/\[...path\]/route.ts \
        apps/web-organic/app/api/coins/\[...path\]/route.ts \
        apps/web-organic/app/api/notify/\[...path\]/route.ts \
        e2e/bff-path-traversal.spec.ts
git commit -m "fix(d14): reject dot-segments in all BFF catch-all proxies (A5 path-traversal hardening)"
```

---

### Task 7: Fix A4 — document AuthCluster as the header integration point

**Files:**
- Modify: `packages/auth-client/src/react.tsx:76-80`

- [ ] **Step 1: Extend the existing doc comment**

Old (lines 76-80):
```tsx
/** Right-side header cluster per the design system: avatar when authed,
 * Login button otherwise. The coins pill is D13's live CoinsBalancePill,
 * placed by each app's own header next to this cluster - AuthCluster no
 * longer renders one itself (its `coinsBalance` field was a D10 placeholder,
 * always 0, now superseded). Drop into HeaderStack's `right` slot. */
```

New:
```tsx
/** Right-side header cluster per the design system: avatar when authed,
 * Login button otherwise. The coins pill is D13's live CoinsBalancePill,
 * placed by each app's own header next to this cluster - AuthCluster no
 * longer renders one itself (its `coinsBalance` field was a D10 placeholder,
 * always 0, now superseded). Drop into HeaderStack's `right` slot.
 *
 * THIS IS THE HEADER INTEGRATION POINT (D14 A4): future header widgets
 * (badges, alerts, balances, whatever) belong as SIBLINGS of <AuthCluster/>
 * in the `right` slot, the way CoinsBalancePill does - never render them
 * FROM INSIDE this component. Two D13 bugs (a duplicate coins pill, then a
 * dead placeholder field) both came from a spec reaching into AuthCluster
 * instead of adding a sibling; don't repeat that. */
```

- [ ] **Step 2: Commit**

```bash
python scripts/check_fully_staged.py
git add packages/auth-client/src/react.tsx
git commit -m "docs(d14): document AuthCluster as the header integration point (A4)"
```

---

### Task 8: Fix Part B#2 — wire the `daily_visit` earn rule on session resume

**Files:**
- Modify: `backend/core/modules/identity/session_router.py`
- Modify: `backend/core/modules/coins/worker.py`
- Test: `backend/core/tests/test_session_router.py`
- Test: `backend/core/tests/test_coins_worker.py`

**Interfaces:**
- Consumes: `shared.events.publish(stream, event_type, payload)` (existing, `shared/events.py:31`); `modules.coins.rules.deterministic_key(rule_code, user_id, *, day=None, ref_id=None)` (existing, `rules.py:29`); `modules.coins.service.award(session, *, user_id, rule_code, ref_id, idempotency_key, now)` (existing, `service.py:131`).
- Produces: new event type `"identity.session_resumed"` on the `"identity"` stream, payload `{"user_id": str}`. `coins/worker.py`'s `handle_event` gains a new branch for it.

- [ ] **Step 1: Write the failing worker test**

Append to `backend/core/tests/test_coins_worker.py`:

```python
async def test_session_resumed_awards_daily_visit(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await handle_event(
        db_session,
        _ev("identity.session_resumed", {"user_id": str(uid)}),
        now=NOW,
    )
    assert await service.balance(db_session, uid) == 5


async def test_session_resumed_is_idempotent_per_day(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    ev = _ev("identity.session_resumed", {"user_id": str(uid)})
    await handle_event(db_session, ev, now=NOW)
    await handle_event(db_session, ev, now=NOW)  # same day, redelivery or a second /me call
    assert await service.balance(db_session, uid) == 5


async def test_session_resumed_awards_again_next_day(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await handle_event(db_session, _ev("identity.session_resumed", {"user_id": str(uid)}), now=NOW)
    next_day = NOW.replace(day=NOW.day + 1)
    await handle_event(db_session, _ev("identity.session_resumed", {"user_id": str(uid)}), now=next_day)
    assert await service.balance(db_session, uid) == 10
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend/core && pytest -q tests/test_coins_worker.py -k session_resumed
```

Expected: FAIL — `handle_event` has no branch for `identity.session_resumed`, balance stays 0.

- [ ] **Step 3: Add the worker branch**

In `backend/core/modules/coins/worker.py`, extend `handle_event` (after the existing `elif event.type == "profile.completed":` block, before the trailing comment):

```python
    elif event.type == "identity.session_resumed":
        uid = uuid.UUID(event.payload["user_id"])
        day = now.strftime("%Y-%m-%d")
        await service.award(
            session,
            user_id=uid,
            rule_code="daily_visit",
            ref_id=day,
            idempotency_key=rules.deterministic_key("daily_visit", uid, day=day),
            now=now,
        )
    # unknown event types: no-op (other consumers own them)
```

- [ ] **Step 4: Run the worker tests again, confirm pass**

```bash
cd backend/core && pytest -q tests/test_coins_worker.py
```

Expected: PASS, all tests including the 3 new ones.

- [ ] **Step 5: Wire the publish call in `session_router.py`'s `/auth/me`**

Before (lines 268-278):
```python
@session_router.get("/me")
async def me(principal: PrincipalDep, session: SessionDep) -> MeOut:
    user = await session.scalar(select(User).where(User.id == principal.user_id))
    assert user is not None  # resolve_web_session proved existence this request
    return MeOut(
        agri_id=user.agri_id,
        handle_is_fallback=user.agri_id.startswith(AG_FALLBACK_PREFIX)
        and not user.agri_id_changed_once,
        can_change_handle=can_change_handle(user.agri_id_changed_once),
        language=await _language_for(session, user.id),
    )
```

After:
```python
@session_router.get("/me")
async def me(principal: PrincipalDep, session: SessionDep) -> MeOut:
    user = await session.scalar(select(User).where(User.id == principal.user_id))
    assert user is not None  # resolve_web_session proved existence this request
    # Best-effort, same pattern as login()'s publishes: a Redis blip must
    # never fail a plain "who am I" read. The coins worker's daily_visit
    # award is idempotent per user+day (rules.deterministic_key), so
    # publishing on every /me call (one per app-header mount) is safe -
    # duplicate awards are impossible even under heavy repeat calls.
    try:
        await publish(EVENT_STREAM, "identity.session_resumed", {"user_id": str(user.id)})
    except Exception as exc:
        logger.warning(
            "identity.session_resumed.publish_failed",
            extra={"extra_fields": {"exc_type": type(exc).__name__}},
        )
    return MeOut(
        agri_id=user.agri_id,
        handle_is_fallback=user.agri_id.startswith(AG_FALLBACK_PREFIX)
        and not user.agri_id_changed_once,
        can_change_handle=can_change_handle(user.agri_id_changed_once),
        language=await _language_for(session, user.id),
    )
```

- [ ] **Step 6: Write the failing session-router test**

Append to `backend/core/tests/test_session_router.py` (mirrors the existing `_events_since`/event-capture helper already used near line 209 — read that helper's exact name and signature in the file before writing this, and reuse it rather than re-implementing):

```python
async def test_me_publishes_session_resumed(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session)
    entries = await _events_since(session)  # drain login()'s own publishes first
    me = await http.get("/auth/me")
    assert me.status_code == 200
    entries = await _events_since(session)
    assert any(e["type"] == "identity.session_resumed" for e in entries)
```

(If the file's actual event-capture helper has a different name/signature than `_events_since`, use the real one — it is used at lines ~205-240 for the login-flow assertions already read during recon.)

- [ ] **Step 7: Run it, confirm pass; run the full session-router file to confirm no regressions**

```bash
cd backend/core && pytest -q tests/test_session_router.py
```

Expected: PASS, including the 2 exact-count tests at lines 209/240 (unaffected — `/me` publishes are unrelated to `login()`'s event set).

- [ ] **Step 8: Commit**

```bash
python scripts/check_fully_staged.py
git add backend/core/modules/identity/session_router.py \
        backend/core/modules/coins/worker.py \
        backend/core/tests/test_session_router.py \
        backend/core/tests/test_coins_worker.py
git commit -m "fix(d14): wire daily_visit coins award on session resume (Part B#2)"
```

---

### Task 9: Fix Part B#3 — surface `AbuseFlag.details` in `AbuseFlagOut`

**Files:**
- Modify: `backend/core/modules/coins/admin_router.py`
- Test: `backend/core/tests/test_coins_admin_router.py`

**Interfaces:**
- `AbuseFlagOut` gains a `details: dict[str, Any]` field; `_abuse_flag_out` populates it from the existing `AbuseFlag.details` model column (already stored, never surfaced — no migration needed).

- [ ] **Step 1: Read the existing abuse-queue test to find its fixture/assertion pattern**

```bash
cd backend/core && grep -n "abuse" tests/test_coins_admin_router.py | head -20
```

- [ ] **Step 2: Write the failing test** — add near the existing abuse-list test (match its actual fixture setup, which the grep above will show; the shape below assumes an `AbuseFlag` row is created with a non-empty `details` dict, matching the model's `server_default="{}"` but explicitly set for this test):

```python
async def test_abuse_queue_surfaces_details(
    api: tuple[httpx.AsyncClient, AsyncSession], staff_headers: dict[str, str]
) -> None:
    # ... reuse this file's existing helper to seed a Referral + AbuseFlag,
    # passing details={"cluster_size": 4, "shared_fingerprint": "abc123"}
    # to the AbuseFlag(...) constructor instead of leaving it at the default.
    response = await api[0].get("/admin/coins/abuse", headers=staff_headers)
    assert response.status_code == 200
    flag = response.json()["items"][0]
    assert flag["details"] == {"cluster_size": 4, "shared_fingerprint": "abc123"}
```

(Adapt the exact seed/auth-header helper names to whatever this file already uses — read it first per Step 1; do not invent new fixtures.)

- [ ] **Step 3: Run it, confirm it fails**

```bash
pytest -q tests/test_coins_admin_router.py -k abuse_queue_surfaces_details
```

Expected: FAIL — `KeyError` or `details` missing from the response body.

- [ ] **Step 4: Add the field**

In `backend/core/modules/coins/admin_router.py`, change:

```python
class AbuseFlagOut(BaseModel):
    id: uuid.UUID
    referral_id: uuid.UUID
    cluster_reason: str
    status: str
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime
```

to:

```python
class AbuseFlagOut(BaseModel):
    id: uuid.UUID
    referral_id: uuid.UUID
    cluster_reason: str
    status: str
    details: dict[str, Any]
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime
```

and add `from typing import Any` to the imports if not already present (check the existing `from typing import Annotated` line and extend it: `from typing import Annotated, Any`).

Update `_abuse_flag_out`:

```python
def _abuse_flag_out(flag: AbuseFlag) -> AbuseFlagOut:
    return AbuseFlagOut(
        id=flag.id,
        referral_id=flag.referral_id,
        cluster_reason=flag.cluster_reason,
        status=flag.status,
        details=flag.details,
        reviewed_by=flag.reviewed_by,
        reviewed_at=flag.reviewed_at,
        created_at=flag.created_at,
    )
```

- [ ] **Step 5: Run the test again, then the full file**

```bash
pytest -q tests/test_coins_admin_router.py
```

Expected: PASS, all tests.

- [ ] **Step 6: Commit**

```bash
python scripts/check_fully_staged.py
git add backend/core/modules/coins/admin_router.py backend/core/tests/test_coins_admin_router.py
git commit -m "fix(d14): surface AbuseFlag.details in admin abuse queue (Part B#3)"
```

---

### Task 10: Fix Part B#5 — remove the dead `AgriUser.coinsBalance` field

**Files:**
- Modify: `packages/auth-client/src/session.ts`
- Modify: `packages/auth-client/src/session.test.ts`
- Modify: `packages/auth-client/src/projection.typetest.ts`
- Modify: `packages/auth-client/src/handlers.test.ts`
- Modify: `packages/auth-client/src/server.test.ts`

- [ ] **Step 1: Read each of the 4 test files' exact `coinsBalance` references before editing**

```bash
grep -n "coinsBalance" packages/auth-client/src/session.test.ts \
  packages/auth-client/src/projection.typetest.ts \
  packages/auth-client/src/handlers.test.ts \
  packages/auth-client/src/server.test.ts
```

- [ ] **Step 2: Remove the field from the type and projector**

In `packages/auth-client/src/session.ts`, change:

```ts
export interface AgriUser {
  agriId: string;
  name: string | null;
  roles: readonly string[];
  /** AgriCoins land in a later spec; headers render this today. */
  coinsBalance: number;
}
```

to:

```ts
export interface AgriUser {
  agriId: string;
  name: string | null;
  roles: readonly string[];
}
```

and:

```ts
export function projectUser(session: SessionPayload): AgriUser {
  return {
    agriId: session.agriId,
    name: session.name,
    roles: [...session.roles],
    coinsBalance: 0,
  };
}
```

to:

```ts
export function projectUser(session: SessionPayload): AgriUser {
  return {
    agriId: session.agriId,
    name: session.name,
    roles: [...session.roles],
  };
}
```

- [ ] **Step 3: Update each test file per what Step 1 showed** — remove `coinsBalance: 0` (or whatever value) from every object literal that constructs/asserts an `AgriUser`, and remove `"coinsBalance"` from any exact key-set assertion (e.g. `Object.keys(user).sort()` or similar in `session.test.ts:17,19,26`). In `projection.typetest.ts:15`, remove `coinsBalance` from the `Equal<keyof AgriUser, ...>` type-level union.

- [ ] **Step 4: Run the package's tests**

```bash
pnpm --filter @agri/auth-client test
pnpm --filter @agri/auth-client typecheck
```

Expected: PASS — no production UI code reads `coinsBalance` (confirmed during recon; the header pill is D13's separate `CoinsBalancePill`), so no app-level changes are needed.

- [ ] **Step 5: Confirm no stray reference remains anywhere**

```bash
grep -rn "coinsBalance" --include="*.ts" --include="*.tsx" . | grep -v node_modules
```

Expected: no output.

- [ ] **Step 6: Commit**

```bash
python scripts/check_fully_staged.py
git add packages/auth-client/src/session.ts packages/auth-client/src/session.test.ts \
        packages/auth-client/src/projection.typetest.ts packages/auth-client/src/handlers.test.ts \
        packages/auth-client/src/server.test.ts
git commit -m "chore(d14): remove dead AgriUser.coinsBalance field (Part B#5)"
```

---

### Task 11: Document Part B#1 defer — referral 20/month cap TOCTOU

**Files:**
- Modify: `backend/core/modules/coins/referrals.py` (comment only — no logic change)
- Modify: `docs/security/sprint1-audit.md` (append the deferred-items table)

- [ ] **Step 1: Confirm the existing comment already documents the race** (`referrals.py:133-140` — read during recon, already explains the TOCTOU and names `pg_advisory_xact_lock` as the fix). No code change needed; only strengthen the comment with an explicit trigger condition:

Append one line to the existing NOTE block in `referrals.py` (after line 140's `... before the count.`):

```python
    # D14 sprint-1 audit: reviewed and explicitly deferred (see
    # docs/security/sprint1-audit.md Part B#1) - safe today because
    # docker-compose.dev.yml runs exactly one `worker` replica. Do NOT scale
    # coins-worker beyond 1 replica without adding the lock above first.
```

- [ ] **Step 2: Append to `docs/security/sprint1-audit.md`'s "Part B deferred-items decisions" section**

```markdown
| # | Item | Decision | Reasoning |
|---|---|---|---|
| 1 | Referral 20/month cap TOCTOU under multiple workers | **Deferred explicitly.** | Safe today: exactly one `worker` (coins) replica in `docker-compose.dev.yml`, events processed serially. `pg_advisory_xact_lock(hashtext('coins_referrer:' \|\| referrer_id))` is the fix, already named in `referrals.py`'s NOTE comment (lines 133-140) — apply it on the "scale coins-worker beyond 1 replica" ticket, not before. A guard comment was added to `referrals.py` pointing back here. |
```

- [ ] **Step 3: Commit**

```bash
python scripts/check_fully_staged.py
git add backend/core/modules/coins/referrals.py docs/security/sprint1-audit.md
git commit -m "docs(d14): explicitly defer referral-cap TOCTOU fix, pin to single-worker constraint (Part B#1)"
```

---

### Task 12: Document Part B#4 defer — unused seeded RBAC perms

**Files:**
- Modify: `docs/security/sprint1-audit.md`

- [ ] **Step 1: Confirm the finding** — `coins.write`/`coins.adjust`/`coins.abuse` (or whatever the actual seeded permission codes are; grep `backend/core/alembic/versions/0011_profiles_rbac_v1.py` and `0012_coins_v1.py` for the exact seeded permission strings before writing this row) are seeded but `admin_router.py`'s `_require_role` gates on raw role names (`SUPER_ADMIN`, `STAFF`), never checking these permission rows.

```bash
grep -n "coins\." backend/core/alembic/versions/0011_profiles_rbac_v1.py backend/core/alembic/versions/0012_coins_v1.py
```

- [ ] **Step 2: Append the decision row**

```markdown
| 4 | Unused seeded RBAC perms (coins.write/adjust/abuse) — admin gates on raw roles, not these perms | **Deferred, harmless.** | The perms exist in the seed data but nothing reads them; `admin_router.py::_require_role` gates on `roles` directly (documented reason: `modules.coins` cannot import `modules.identity`'s `require_permission`, per the import-linter independence contract). No security gap — the raw-role gate is at least as strict. Revisit once a shared, cross-module permission-check helper exists (Sprint-2+ concern, not scoped here). |
```

- [ ] **Step 3: Commit**

```bash
python scripts/check_fully_staged.py
git add docs/security/sprint1-audit.md
git commit -m "docs(d14): defer unused seeded RBAC perms cleanup (Part B#4)"
```

---

### Task 13: Document Part B#6 defer — ta/hi coin-reason translations

**Files:**
- Modify: `docs/security/sprint1-audit.md`

- [ ] **Step 1: Confirm current state** — `packages/ui/src/i18n/messages/ta.json:186-198` (and the `hi.json` equivalent) already contain real Tamil/Hindi text for every `coins.reason.*` key (`signup_complete`, `profile_100`, `daily_visit`, `referral_referrer`, `referral_referee`, `redeem`, `manual_adjust`, `compensation`, `unknown`) — these are provisional/best-effort translations, not literally missing, but unreviewed by a native content pass.

- [ ] **Step 2: Append the decision row**

```markdown
| 6 | ta/hi coin-reason translations are provisional (not content-reviewed) | **Deferred to content pass.** | `packages/ui/src/i18n/messages/{ta,hi}.json` already have non-empty Tamil/Hindi strings for every `coins.reason.*` key (not blank placeholders) but have not been reviewed by a native-speaker content pass. Not a launch blocker. Flagged here for the D27/D39 seed-translation work (`docs/Execution schedule v5.MD:229`, "maintained glossary EN↔TA↔HI") to pick up. |
```

- [ ] **Step 3: Commit**

```bash
python scripts/check_fully_staged.py
git add docs/security/sprint1-audit.md
git commit -m "docs(d14): defer ta/hi coin-reason translation content review (Part B#6)"
```

---

### Task 14: Fix Critical/High findings from the A6 sweep (Task 5)

**Files:** Determined by Task 5's confirmed findings — cannot be enumerated before Task 5 runs.

**Process (repeat per confirmed Critical/High finding from Task 5):**

- [ ] **Step 1: For each `confirmed` Critical/High row in `docs/security/sprint1-audit.md`'s A6 table, write a failing test that reproduces it** in the relevant existing test file (`test_otp_*.py`, `test_oauth_*.py`, `test_session_*.py`, `test_rbac_*.py`/`test_admin_router.py`, `test_coins_*.py`, `test_audit_*.py`, `test_notify_*.py` — match to the finding's area).

- [ ] **Step 2: Run it, confirm it fails, apply the minimal fix in the implicated module** (never widen scope beyond the specific finding — no drive-by refactors).

- [ ] **Step 3: Run the fixed file's full test suite, confirm green, confirm no other file's tests regressed** (`cd backend/core && pytest -q` full run after each fix, not just the touched file).

- [ ] **Step 4: Update the finding's row in `docs/security/sprint1-audit.md`'s A6 table: `Status: fixed`, with the commit SHA and a one-line description of the fix.**

- [ ] **Step 5: Commit per finding** (one commit per fix, not one giant commit — keeps `git bisect` useful and matches "frequent commits"):

```bash
python scripts/check_fully_staged.py
git add <touched files>
git commit -m "fix(d14): <one-line description of the specific A6 finding fixed>"
```

- [ ] **Step 6: After every confirmed Critical/High is `fixed`, re-run the full backend suite once more and update the audit doc's summary line to state the final count: "N Critical/High found, N fixed, 0 open."** This is the evidence Task 18 (Gate 2) cites.

---

### Task 15: Part C — full automated suite

**Files:** None (verification task).

- [ ] **Step 1: Backend unit/integration suite**

```bash
cd backend/core && ruff format --check . && ruff check . && mypy . && lint-imports && python scripts/migrate_check.py && pytest -q -m "not slow"
```

Expected: all green. If anything regressed from Tasks 6-14's changes, fix it before continuing (do not proceed with red tests).

- [ ] **Step 2: Coins storm test (now the `backend-storm` required check)**

```bash
cd backend/core && pytest -q -m "slow"
```

Expected: `tests/test_coins_storm.py::test_storm_no_drift_no_negative` PASS.

- [ ] **Step 3: Audit chain tamper + PII redaction + event-count regression tests**

```bash
cd backend/core && pytest -q tests/test_audit_integrity.py tests/test_telemetry.py tests/test_session_router.py tests/test_identity_user_registered.py tests/test_notify_consumers.py
```

Expected: all green, including the two exact-count tests noted in A3 (unaffected by Task 8's `/me`-only publish).

- [ ] **Step 4: Auth Playwright E2E + cross-domain SSO E2E**

```bash
pnpm exec playwright install chromium --with-deps  # if not already installed locally
pnpm run e2e
```

Expected: `e2e/auth.spec.ts`, `e2e/sso.spec.ts`, and the new `e2e/bff-path-traversal.spec.ts` all pass.

- [ ] **Step 5: Record every command's pass/fail output in `docs/security/sprint1-audit.md` under a new "Part C — full-suite results" heading, or in `docs/gates/gate2.md` directly (Task 18 decides final placement — draft it in the audit doc for now, move if needed).**

---

### Task 16: Manual burst tests

**Files:** None (manual verification, evidence captured into `docs/gates/gate2.md` directly since Task 18 needs it).

- [ ] **Step 1: Scripted OTP flood — confirm limits fire**

With the dev stack running (`docker compose -f docker-compose.dev.yml up -d`), fire more OTP requests than the configured per-phone/per-IP limit in a tight loop against `POST /auth/otp/request` for one phone number, and confirm the response transitions to a 429/rate-limited status at the expected threshold (read the actual limit from `modules/identity/otp_service.py` or its rate-limit config before running, so the loop count and expected trip point are exact, not guessed).

```bash
for i in $(seq 1 15); do curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/auth/otp/request -H "content-type: application/json" -d '{"phone":"+919876543210"}'; done
```

Record the exact request number where the status code changes, and the final status code, in `docs/gates/gate2.md`.

- [ ] **Step 2: Scripted coins award race — confirm no drift**

This is already covered automatically by `test_coins_storm.py` (Task 15 Step 2, 10k concurrent awards, asserts final balance == expected and never negative). For the MANUAL burst variant the spec asks for (distinct from the automated CI job), fire ~50 concurrent `profile.completed` events for the SAME user_id directly at a locally running `coins-worker` (or invoke `handle_event` concurrently via a small `asyncio.gather` script against a real Postgres, not the test DB) and confirm the balance only reflects one `profile_100` award (idempotency key collapses the rest). Record the before/after balance and event count in `docs/gates/gate2.md`.

- [ ] **Step 3: Paste both pieces of evidence (exact commands + real output, not paraphrased) into `docs/gates/gate2.md`'s corresponding checklist items (Task 18 creates the file structure; this step's output is pasted into it).**

---

### Task 17: Committed-tree verification

**Files:** None (verification task, scratch directory only).

- [ ] **Step 1: Archive the committed HEAD of the branch (after all Tasks 1-16 are committed) and extract to scratch**

```bash
git archive HEAD -o "$TEMP/d14-verify.tar" 
mkdir -p "$TEMP/d14-verify"
tar -xf "$TEMP/d14-verify.tar" -C "$TEMP/d14-verify"
```

(Use the scratchpad directory from this session's environment, not a hardcoded `/tmp`, if running on Windows via the Bash tool — Git Bash accepts POSIX paths for its own `$TEMP`, or use `C:\Users\arunp\AppData\Local\Temp\claude\...\scratchpad`.)

- [ ] **Step 2: Load the migration chain from the archive (proves alembic history matches what's committed, not just what's on disk)**

```bash
cd "$TEMP/d14-verify/backend/core" && alembic -c alembic.ini history
```

Expected: same linear 0001→0015 chain documented in Task 4's A1 section, loaded from the archive, not the working tree.

- [ ] **Step 3: Run the full backend + storm suite against the archived copy** (needs its own venv + a throwaway Postgres/Redis, or point `ALEMBIC_DATABASE_URL`/`DATABASE_URL` at the same dev containers used elsewhere in this plan — either is fine as long as it's the ARCHIVED code executing, not the working tree)

```bash
cd "$TEMP/d14-verify/backend/core" && pip install -e .[dev] && pytest -q -m "not slow" && pytest -q -m "slow"
```

Expected: all green — proves "committed == what was tested" (the exact D13 lesson this task exists to re-prove).

- [ ] **Step 4: Record the archive verification's pass/fail summary in `docs/gates/gate2.md`'s corresponding checklist item, and clean up the scratch extraction.**

```bash
rm -rf "$TEMP/d14-verify" "$TEMP/d14-verify.tar"
```

---

### Task 18: Part D — write `docs/gates/gate2.md`

**Files:**
- Create: `docs/gates/gate2.md`

- [ ] **Step 1: Write the gate doc, following `docs/runbooks/gate-1.md`'s structure** (title+date header, one-line DoD, numbered evidence sections with real command output pasted in — not paraphrased — closing "Known gaps" section):

```markdown
# GATE 2 evidence (D14, 2026-07-14)

Definition of done: zero Critical/High open at tag; backend-storm required
before tag; committed tree verified == tested tree; every box below checked
and dated; v0.2.0 promotable from main.

## Checklist

- [ ] one AgriID -> login on all 3 site domains (localhost multi-port) via SSO — evidence: Task 15 Step 4 (`e2e/sso.spec.ts` output)
- [ ] logout-everywhere across apps — evidence: `e2e/sso.spec.ts` + `test_session_router.py::test_logout_everywhere_one_request_cycle` (Task 15 Steps 3-4)
- [ ] OTP abuse suite green incl. manual burst — evidence: Task 15 (automated) + Task 16 Step 1 (manual, paste real output)
- [ ] 10k-award storm zero drift — AND backend-storm is a required status check — evidence: Task 15 Step 2 (test output) + Task 2 (doc update; note the free-plan enforcement gap is unresolved pending owner action, per `docs/runbooks/branch-protection.md`)
- [ ] migration chain verified on the COMMITTED tree (A1) — evidence: Task 4 A1 section + Task 17 Step 2
- [ ] app_rt grant matrix correct across all 4 schemas; no service connects as `app` at runtime (A2) — evidence: Task 4 A2 section
- [ ] exactly one coins pill per header; AuthCluster documented as the header integration point (A4) — evidence: Task 4 A4 section + Task 7
- [ ] public_routes.txt hand-reviewed — every public route justified in one line — evidence: paste the 8-route list from `backend/core/public_routes.txt` here with a one-line justification per route (auth flow routes only: /health, /health/deep, /metrics, /auth/otp/request, /auth/otp/verify, /auth/login, /authorize, /token, /oauth/revoke, /.well-known/jwks.json)
- [ ] audit verify_chain() clean over sprint's real data — evidence: Task 15 Step 3 (`test_audit_integrity.py`) output, plus running `scripts/verify_audit_chain.py` directly against the dev DB and pasting its output
- [ ] git status clean, zero AM files, committed tree == tested tree — evidence: `python scripts/check_fully_staged.py` final run + Task 17

## Known gaps carried forward

- Branch protection / rulesets remain unenforced on the free GitHub plan
  (`docs/runbooks/branch-protection.md` Known Gap, unchanged since Gate 1) —
  `backend-storm` is documented as required (Task 2) but activation is an
  owner action on GitHub UI, still pending as of this gate.
- `web-admin` and `web-agri` are not in `e2e/playwright.config.ts`'s
  `webServer` list, so their BFF proxy hardening (Task 6) was verified by
  unit-identical code + one manual curl each, not full e2e — pre-existing
  gap, not introduced by D14.
- Referral-cap TOCTOU (Part B#1) and unused RBAC perms (Part B#4) are
  explicit defers — see `docs/security/sprint1-audit.md`.
```

- [ ] **Step 2: Fill in every `- [ ]` with real evidence (command + actual output) as each prior task's evidence becomes available — do not check a box without pasted real output.**

- [ ] **Step 3: Commit**

```bash
python scripts/check_fully_staged.py
git add docs/gates/gate2.md
git commit -m "docs(d14): record Gate 2 evidence"
```

---

### Task 19: Part E — PR `feat/d14-sprint1-hardening` → `dev`

**Files:** None.

- [ ] **Step 1: Final pre-PR check**

```bash
python scripts/check_fully_staged.py
git status
cd backend/core && pytest -q -m "not slow" && pytest -q -m "slow" && cd ../..
pnpm run e2e
```

All must be green before opening the PR.

- [ ] **Step 2: Push and open the PR (human checkpoint — `gh` unavailable)**

```bash
git push -u origin feat/d14-sprint1-hardening
```

Print for the user:

```
gh is not available here. Please open the PR manually:
  https://github.com/oneuni-in/agri-ecosystem/compare/dev...feat/d14-sprint1-hardening?expand=1
Title: D14: Sprint-1 hardening + Gate 2
Body: summarize Tasks 1-18 (pre-flight, A1-A6 audit, Part B fixes/defers,
full-suite + manual + committed-tree verification, Gate 2 evidence).
Merge only after all 9 required checks (including backend-storm) are green.
```

- [ ] **Step 3: Wait for the user to confirm CI is green and the PR is merged into `dev` before Task 20.**

---

### Task 20: Part E — promote `dev` → `main`, tag `v0.2.0` (human-only)

**This task is NOT executed by the agent.** Per `CLAUDE.md`: "dev → main promotion is done by the human only" and "Never open PRs to main." Print the exact sequence for the user and stop:

```
D14 work is merged to dev. Promotion to main is your call to make and run:

1. gh pr create --base main --head dev --title "v0.2.0: Sprint 1 complete" \
     --body "Promotes dev (D06-D14) to main. Gate 2: docs/gates/gate2.md."
   (or open the compare URL manually:
    https://github.com/oneuni-in/agri-ecosystem/compare/main...dev?expand=1)
2. Review and merge the PR yourself.
3. After merge:
     git checkout main && git pull
     git tag v0.2.0
     git push origin v0.2.0
4. Delete dev-backup-pre-sync (local) once v0.2.0 is confirmed on main:
     git branch -d dev-backup-pre-sync
5. Request the Sprint 2 pack (D15-D22) when ready.
```

- [ ] **Step 1: Print the above to the user and end the plan here.**

---

## Self-review notes (from plan authoring)

- A1/A2/A4 needed no code fix — recon already proved them clean on this
  branch; Task 4 documents evidence rather than inventing fix work that
  isn't needed (measured choice, per `CLAUDE.md`).
- A5's guard runs before the auth check specifically so it's testable
  without a live session — this is a deliberate design choice made during
  planning, not in the original spec text, and is called out inline in
  Task 6 Step 3's reasoning.
- Task 14 cannot contain literal code diffs because Task 5's findings are
  unknown until that audit runs; it instead specifies the exact process
  (reproduce → fix → full-suite → document → commit-per-finding) so no
  step is a bare "handle it" placeholder.
- Every task that touches git history-affecting operations on `dev` (Tasks
  1, 19, 20) is written as an explicit human checkpoint, consistent with
  this environment's git safety rules and `CLAUDE.md`'s promotion rule.
