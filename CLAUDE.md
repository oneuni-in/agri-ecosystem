Endpoints are private, rate-limited, and validated unless explicitly
marked public. All lists are cursor-paginated; all IDs are UUIDv7; all
user content defaults to pending. All public pages are SSR/ISR with
JSON-LD, immutable slugs, and pass Lighthouse 90 in CI. When in doubt:
boring choice, reversible choice, measured choice.

## Git workflow
- NEVER commit to main or dev directly. main and dev are protected.
- Every work package: create branch feat/dXX{a|b}-short-name from dev.
- Commit with conventional commits. Push branch, open PR targeting dev.
- Never open PRs to main. dev → main promotion is done by the human only.