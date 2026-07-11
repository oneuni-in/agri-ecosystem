# Branch protection verification (SPEC D04-G)

`main` and `dev` are protected: **no direct pushes, PRs only, all gates
green.** The gates themselves live in `.github/workflows/ci.yml` — a
protected file in the sense that weakening or deleting a gate is a visible
diff in a PR that itself must pass review (threat model: gate erosion under
deadlines).

## Current enforcement status — KNOWN GAP (2026-07-10)

The ruleset **"secure branch rules"** exists (Settings → Rules → Rulesets),
targets `dev` + `main`, is set to **Active**, and matches the settings below.
**BUT GitHub does not enforce rulesets (or classic branch protection) on
private repos under the free org plan.** Decision (owner, 2026-07-10): stay
on the free plan for now — **enforcement is convention-based until the org
upgrades to GitHub Team or the repo goes public**, at which point the saved
ruleset activates with zero reconfiguration.

What this means day-to-day while the gap exists:

- Direct pushes to `dev`/`main` are *physically possible*; the CLAUDE.md rule
  (never commit to main/dev, PRs only) is the actual barrier.
- CI still runs on every PR and shows red/green — but a red PR *can* be
  merged. Do not.
- Revisit at GATE 1 (D05): re-evaluate the Team upgrade before the first
  dev → main promotion.

## Required settings (implemented as ruleset "secure branch rules")

For **both** `main` and `dev`:

- [x] Require a pull request before merging (≥ 1 approval)
- [x] Require status checks to pass before merging, **strict** (branch up to
      date), with these required checks (exact job names from `ci.yml`):
  - `web`
  - `design-tokens`
  - `backend`
  - `public-routes`
  - `security`
  - `lighthouse`
  - `e2e-auth`
  - `conventional-commits`
- [x] Require conversation resolution before merging
- [x] Do not allow bypassing the above settings (include administrators)
- [x] Block force pushes / deletions (default under protection)

For `main` additionally: only the human promotes `dev` → `main` (CLAUDE.md);
no PR from feature branches targets `main`.

Conventional commits are enforced by the `conventional-commits` job (PR title
+ every branch commit), so the requirement holds regardless of merge
strategy.

## How to verify (run after changing settings, and periodically)

With the GitHub CLI (any machine with `gh`):

```sh
gh api repos/oneuni-in/agri-ecosystem/branches/dev/protection | python -m json.tool
gh api repos/oneuni-in/agri-ecosystem/branches/main/protection | python -m json.tool
```

Check in the output: `required_pull_request_reviews.required_approving_review_count >= 1`,
`required_status_checks.strict == true`, the eight contexts above listed in
`required_status_checks.contexts`, and `enforce_admins.enabled == true`.

No-CLI fallback: attempt `git push origin HEAD:dev` from a feature branch —
it must be rejected; and confirm on a test PR that all eight checks appear
in the merge box as **Required**. *While the free-plan gap is open (see
above), the push will NOT be rejected — that is the known gap, not a
misconfiguration.*

For rulesets, the CLI check is:

```sh
gh api repos/oneuni-in/agri-ecosystem/rulesets | python -m json.tool
```

## Verification log

| Date | Branch | Verified by | Notes |
| --- | --- | --- | --- |
| 2026-07-10 | dev, main | (pending human verification after D04 merges) | initial gate set: 7 required checks |
| 2026-07-10 | dev, main | owner | ruleset "secure branch rules" created, Active, empty bypass list; NOT enforced on free-plan private repo — convention-based until Team upgrade (see Known Gap) |
| 2026-07-11 | dev, main | (pending human: add `e2e-auth` to the ruleset's required checks) | D09 adds the 8th required check: `e2e-auth` (Playwright auth flows) |
