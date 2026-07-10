# Branch protection verification (SPEC D04-G)

`main` and `dev` are protected: **no direct pushes, PRs only, all gates
green.** The gates themselves live in `.github/workflows/ci.yml` — a
protected file in the sense that weakening or deleting a gate is a visible
diff in a PR that itself must pass review (threat model: gate erosion under
deadlines).

## Required settings (GitHub → Settings → Branches → add rule)

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
`required_status_checks.strict == true`, the seven contexts above listed in
`required_status_checks.contexts`, and `enforce_admins.enabled == true`.

No-CLI fallback: attempt `git push origin HEAD:dev` from a feature branch —
it must be rejected with `protected branch hook declined`; and confirm on a
test PR that all seven checks appear in the merge box as **Required**.

## Verification log

| Date | Branch | Verified by | Notes |
| --- | --- | --- | --- |
| 2026-07-10 | dev, main | (pending human verification after D04 merges) | initial gate set: 7 required checks |
