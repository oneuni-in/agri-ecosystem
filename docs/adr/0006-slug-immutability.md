# ADR-0006: Immutable slugs + recorded 301 redirects

**Status:** Accepted (2026-07-10) · **Reversal cost:** one-way door — SEO equity and shared links depend on it; "mutable slugs later" would orphan every published URL the moment someone renames an entity.

## Context
The growth engine is programmatic SEO (vertical × geo landing pages). A slug change that 404s an indexed URL burns ranking that takes months to earn. Constitution: all public pages have immutable slugs.

## Decision
Slugs never change in place. A rename records a redirect row (`shared/slugs.py`), and `SlugRedirectMiddleware` (`shared/middleware.py`) 301s any GET/HEAD that would otherwise 404 — the happy path never pays the lookup. Redirect history survives entity renames indefinitely.

## Consequences
- Indexed URLs and shared links keep working forever; link equity flows through 301s.
- The redirect table grows monotonically — trivial storage, and it is the audit trail.
- Renames are slightly heavier (insert + new slug) — the right trade for a content platform.
- No revisiting trigger: weakening this silently is the failure mode, hence the middleware owns it centrally.
