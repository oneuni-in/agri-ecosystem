# @agri/auth-client

AgriID SSO via the BFF (Backend-for-Frontend) pattern (D10). Each Next.js
app runs its own OAuth2 authorization-code + PKCE dance inside its own route
handlers (`createHandlers(cfg)`); the browser never sees an access or
refresh token — only an httpOnly, encrypted session cookie scoped to that
app's origin.

## BFF pattern & threat model

- **XSS token exfiltration** — killed by storage, not sanitization: access
  and refresh tokens live only inside a JWE (`dir` + `A256GCM`, `jose`)
  sealed into an `HttpOnly` cookie (see `src/cookies.ts`). No JS on any app
  page ever reads a token; there is nothing for an injected script to steal.
- **CSRF** — killed by OAuth `state` (bound to a short-lived, sealed `_tx`
  cookie and checked byte-for-byte on callback) plus PKCE (`S256`
  `code_challenge`/`code_verifier`), so a forged callback request can't
  complete a token exchange even if the attacker can make the browser hit it.
- **Zombie sessions after logout-everywhere** — killed by two layers: (1) a
  back-channel logout push from id.agri.in verified against its JWKS
  (`src/jwks.ts`) that revokes the session immediately in each app's
  in-memory denylist (`src/denylist.ts`); (2) as a safety net for any missed
  or delayed push, `/api/auth/me` re-checks on every request and the access
  token itself dies within ~15 minutes regardless, forcing a refresh-token
  rotation that a revoked family will fail.

The browser only ever receives a 302, a `Set-Cookie`, or a JSON projection
(`AgriUser` — no internal UUID, no phone, no tokens; see `src/session.ts`).

## Env vars (per app)

Each app's `lib/auth.ts` calls `createAgriAuth(config)` and reads these at
process start:

| Var | Required | Meaning |
| --- | --- | --- |
| `APP_ORIGIN` | dev: no (defaults per app) / prod: yes | This app's own browser-facing origin, e.g. `https://milk.in`. Used to build the OAuth `redirect_uri` and to redirect back after login. |
| `ID_PUBLIC_ORIGIN` | dev: no / prod: yes | Browser-facing AgriID origin — `/authorize` and the login UI live here. |
| `API_BASE_URL` | dev: no / prod: yes | Server-to-server AgriID API origin (`idInternalOrigin` internally) — `/token`, `/oauth/revoke`, JWKS. Called from the Next server only, never the browser. |
| `AUTH_SESSION_SECRET` | dev: no (falls back to a fixed dev constant) / **prod: yes, per app** | Key material for sealing this app's session cookie. `resolveConfig()` is resolved lazily on first request and throws then if `NODE_ENV=production` and this is unset (not at import/build time, so `next build` never evaluates it). Each app must get its **own** value — sharing one across apps would let a sealed cookie from one app decrypt on another. |

## Prod domain map

`id.agri.in` serves **both** the authorize/login UI and the token API —
`idPublicOrigin` and `idInternalOrigin` resolve to the same origin,
`https://id.agri.in`, in production.

| App | `clientId` | `APP_ORIGIN` (prod) |
| --- | --- | --- |
| web-agri | `web-agri` | `https://agri.in` |
| web-milk | `web-milk` | `https://milk.in` |
| web-organic | `web-organic` | `https://organicstore.in` |
| web-admin | `web-admin` | `https://admin.agri.in` |
| web-id | n/a (issuer, not a BFF client) | `https://id.agri.in` |

Per app, derived from `APP_ORIGIN`:

- Callback (redirect_uri): `{APP_ORIGIN}/api/auth/callback` — must match a
  seeded OAuth client redirect URI exactly (migration 0009 seeds the dev
  localhost URIs and, when `app_env == "prod"`, these prod URIs).
- Back-channel logout: `{APP_ORIGIN}/api/auth/backchannel-logout`.

Cookies are **per-app, host-only** by design — no cross-TLD or cross-subdomain
sharing. `agri.in`, `milk.in`, `organicstore.in`, and `admin.agri.in` are
distinct registrable domains, so there is no `Domain=` attribute that could
span them even if it were desirable; each app's session cookie is only ever
sent to that app's own origin.

## Dev stand-in (localhost multi-port)

There is no multi-TLD setup in dev, so distinct ports stand in for distinct
prod domains. All apps still get real, independent cookies because
`localhost` is port-blind but the cookie *names* are derived per `clientId`
(`{clientId without "web-"}_session`, e.g. `milk_session`, `organic_session`).

| Port | App |
| --- | --- |
| 3000 | web-milk |
| 3001 | web-organic |
| 3002 | web-agri |
| 3003 | web-id (authorize UI + rewrites `/authorize` to the API) |
| 3004 | web-admin |
| 8000 | api |

## Known v1 limits

- **In-memory denylist is per-process** (`src/denylist.ts`). It is not
  shared across app instances/replicas, so a logout-everywhere push that
  lands on one process won't revoke a session held by another process of the
  same app. The ~15-minute access-token horizon in `/api/auth/me` is the
  safety net that bounds the exposure regardless of which process a request
  hits.
- **Silent-SSO suppression marker is per-tab** (`SSO_MARKER` in
  `src/react-helpers.ts`, stored in `sessionStorage` — tab-scoped and it
  survives the probe's full-page redirect; the value is a boolean `"1"`,
  never a token). Opening a new tab re-attempts the silent `prompt=none`
  probe once, even right after a failed probe in another tab.
