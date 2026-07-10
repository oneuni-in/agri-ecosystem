# ADR-0002: AgriID — one SSO identity across all apps

**Status:** Accepted (2026-07-10) · **Reversal cost:** one-way door in practice — after launch, migrating user accounts and credentials to a different identity topology is a data migration with user-visible breakage. Decided now, before any users exist, which is the cheap moment.

## Context
Five apps (agri, milk, organic, id, admin) serve overlapping audiences: a dairy farmer is also an agri-input buyer. Separate accounts per app would fragment users, reviews, coins, and location preferences, and quintuple the auth attack surface.

## Decision
One identity — AgriID — owned by the `identity` module and consumed by every app through `@agri/auth-client` (currently a typed stub; OAuth2 Authorization Code + PKCE lands in Sprint 1, D06–D14). Roles are coarse (`anon/user/vendor/moderator/admin`) with RBAC detail in the identity module. No app grows its own auth.

## Consequences
- One profile, one language preference, one location context shared ecosystem-wide; coins and reputation transfer across verticals.
- The identity module becomes critical-path: its availability bounds every app's login.
- We give up per-app auth shortcuts; every session flows through one token surface.
- Revisit only if a legal/compliance boundary forces identity separation for a vertical.
