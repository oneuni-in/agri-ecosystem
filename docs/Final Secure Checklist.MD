# Secure Build Checklist
**Stack:** Next.js 15 (App Router) · FastAPI · PostgreSQL 16 · Redis 7 · Hostinger VPS · Cloudflare · Razorpay · Cloudflare R2
**Applies to:** Agri.in, Milk.in, OrganicStore.in, Mattress.in

---

## 1. DATABASE (PostgreSQL 16)

- [ ] PostgreSQL bound to `127.0.0.1` only (`listen_addresses = 'localhost'` in postgresql.conf)
- [ ] Port 5432 blocked in firewall (`ufw deny 5432`)
- [ ] App connects via a dedicated DB user — NOT `postgres` superuser
- [ ] App DB user has only SELECT / INSERT / UPDATE / DELETE on app schema — no DROP, no CREATE, no superuser
- [ ] Separate DB user for Alembic migrations (has DDL rights; app user does not)
- [ ] Strong random DB password (32+ chars), stored only in `.env`
- [ ] Passwords hashed with bcrypt or argon2 — never plaintext, never reversible encryption
- [ ] Highly sensitive fields (govt IDs, bank details) encrypted at application level before insert (Fernet/AES-256), keys in `.env`
- [ ] `scram-sha-256` auth in pg_hba.conf (not `trust`, not `md5`)
- [ ] Automated daily backups, encrypted, stored OFF the VPS (R2 bucket or separate location)
- [ ] Backup restore tested at least once (a backup you haven't restored is a hope, not a backup)
- [ ] Query logging of slow/failed queries enabled for anomaly detection

## 2. REDIS 7

- [ ] Bound to `127.0.0.1` only
- [ ] `requirepass` set with strong password
- [ ] Dangerous commands disabled: `rename-command FLUSHALL ""`, `CONFIG`, `KEYS`
- [ ] Port 6379 blocked in firewall
- [ ] No sensitive plaintext data cached (or short TTLs if unavoidable)

## 3. BACKEND (FastAPI)

### Input & queries
- [ ] Every request body/query param validated by Pydantic v2 model — zero exceptions
- [ ] All DB access through SQLAlchemy 2 async ORM / parameterized queries — no f-string SQL, no `.raw()` with user input
- [ ] File uploads: whitelist extensions + MIME check + max size + randomized filenames; stored in R2, never on app filesystem
- [ ] Reject unexpected fields (`model_config = ConfigDict(extra='forbid')` on sensitive models)

### Auth & sessions (AgriID SSO)
- [ ] JWT access tokens short-lived (15 min), refresh tokens rotated on use
- [ ] JWT secret 64+ random chars, in `.env`, different per environment
- [ ] Tokens invalidated server-side on logout / password change (Redis denylist)
- [ ] OTP/login rate-limited: max 5 attempts per phone per 15 min (Redis counter)
- [ ] Account lockout / progressive delay after repeated failures
- [ ] Password reset tokens single-use, expire in 15 min

### Authorization (the #1 real-world bug)
- [ ] EVERY endpoint touching user data verifies ownership: `WHERE user_id = current_user.id` — never trust IDs from the URL/body
- [ ] Admin endpoints check role server-side on every request (not just hidden in UI)
- [ ] Object-level checks on updates/deletes (user A cannot modify user B's record by changing an ID)
- [ ] Two-tier publishing rules enforced in backend, not frontend

### API hardening
- [ ] Global rate limiting per IP (e.g., slowapi + Redis)
- [ ] CORS locked to exact production domains — no `*`
- [ ] Error responses generic to client ("Something went wrong"); full stack traces only in server logs
- [ ] `/docs` and `/redoc` disabled or auth-gated in production
- [ ] Request size limits enforced (reject giant payloads)
- [ ] Structured logging of: auth failures, admin actions, permission denials, payment events
- [ ] Razorpay webhook signature verified on every webhook; payment amounts verified server-side, never trusted from client

## 4. FRONTEND (Next.js 15)

- [ ] Session tokens in httpOnly + Secure + SameSite=Lax cookies — NEVER localStorage
- [ ] No `dangerouslySetInnerHTML` with user-generated content (if unavoidable, sanitize with DOMPurify)
- [ ] All frontend validation duplicated on backend (frontend validation = UX only)
- [ ] No secrets in frontend code — only `NEXT_PUBLIC_` vars that are truly public
- [ ] CSRF protection on state-changing requests (SameSite cookies + token for sensitive actions)
- [ ] Security headers set (next.config or middleware):
  - [ ] `Content-Security-Policy`
  - [ ] `Strict-Transport-Security` (HSTS)
  - [ ] `X-Frame-Options: DENY`
  - [ ] `X-Content-Type-Options: nosniff`
  - [ ] `Referrer-Policy: strict-origin-when-cross-origin`
- [ ] External links with `rel="noopener noreferrer"`
- [ ] Admin panel on separate path/subdomain, server-side role check on every page load

## 5. SERVER (Hostinger VPS / Ubuntu)

- [ ] SSH key-only login (`PasswordAuthentication no`)
- [ ] Root login disabled (`PermitRootLogin no`); use sudo user
- [ ] fail2ban installed and active on SSH
- [ ] `ufw` default deny incoming; allow only 22 (or custom SSH port), 80, 443
- [ ] Ports 80/443 restricted to Cloudflare IP ranges only (so attackers can't bypass Cloudflare by hitting the VPS IP)
- [ ] Unattended security upgrades enabled (`unattended-upgrades`)
- [ ] App runs as non-root user
- [ ] `.env` files chmod 600, owned by app user, NEVER committed to git (`.gitignore` verified)
- [ ] No secrets in git history (scan with `gitleaks` once)
- [ ] Separate `.env` per environment; production secrets never on dev machine

## 6. CLOUDFLARE / NETWORK

- [ ] Proxy (orange cloud) ON for all DNS records — real server IP hidden
- [ ] SSL mode: Full (Strict) with valid origin certificate
- [ ] Always Use HTTPS + HSTS enabled
- [ ] WAF managed rules enabled (free tier includes basics)
- [ ] Rate limiting rule on `/api/auth/*` endpoints
- [ ] Bot Fight Mode ON
- [ ] Cloudflare R2 buckets private; files served via signed URLs or proxy — no public bucket listing

## 7. PAYMENTS (Razorpay)

- [ ] Order amount created server-side; client can never set the price
- [ ] Payment signature verified server-side (`razorpay.utility.verify_payment_signature`)
- [ ] Webhook secret verified on every webhook call
- [ ] Idempotency: duplicate webhook deliveries don't double-credit AgriCoins/subscriptions
- [ ] Live keys only in production `.env`; test keys everywhere else

## 8. OPERATIONS & HUMAN LAYER

- [ ] Admin accounts: strong unique passwords + 2FA (TOTP)
- [ ] One admin account per human (when team grows) — no shared logins
- [ ] Audit log for admin actions (who approved/published/deleted what, when)
- [ ] Dependency updates monthly: `npm audit` / `pip-audit`
- [ ] Pin dependency versions (lockfiles committed)
- [ ] Incident plan written: how to rotate all secrets fast if a key leaks (DB password, JWT secret, Razorpay keys, R2 keys)
- [ ] Data minimization: don't collect/store fields you don't need — data you don't have can't leak
- [ ] Privacy policy + DPDP Act (India) compliance reviewed before launch (consent, data deletion requests)

---

## SECURITY NON-NEGOTIABLES (paste into every Claude Code feature prompt)

```
SECURITY NON-NEGOTIABLES:
1. Every endpoint touching user data MUST verify ownership (current_user.id) — never trust IDs from URL/body.
2. All input through Pydantic v2 models; all DB access through SQLAlchemy ORM — no raw SQL from user input.
3. Auth tokens in httpOnly/Secure/SameSite cookies only; auth endpoints rate-limited via Redis.
4. No secrets in code or git — .env only. Generic error messages to client; details to server logs only.
```

---

## PRE-LAUNCH FINAL PASS (run per platform: Milk.in → OrganicStore.in → Agri.in)

- [ ] Try accessing another user's record by changing IDs in URL/API — must fail
- [ ] Try hitting VPS IP directly (bypassing Cloudflare) — must fail
- [ ] Try connecting to Postgres/Redis from outside — must fail
- [ ] Confirm `/docs` not public
- [ ] Confirm client-side price tampering doesn't change Razorpay order amount
- [ ] Run `npm audit` + `pip-audit` — no high/critical vulns
- [ ] Confirm backup restore works
- [ ] Check response headers on live site (securityheaders.com)