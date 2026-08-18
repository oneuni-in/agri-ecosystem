# AG-A12 — do the farm calculators actually work offline?

**Status: yes, on a production build, for a visitor who has opened `/tools`
before losing signal. Proven by run, not by argument.**

```
node scripts/verify-offline-tools.mjs
  100000 @ 11% over 60m  ->  ₹2,174
  PASS — computed ₹2,174 offline.
```

This file exists because the row was previously carried on evidence that did
not support it, and the gap only showed up when someone finally switched the
network off.

## What the row used to rest on

Two real proofs, neither of which is the claim:

1. **12 unit tests** on the formulas. Proves the arithmetic.
2. **An e2e spec** asserting zero `fetch`/`xhr` during a computation. Proves
   the calculators are network-*pure*.

Network-pure is not the same as works-offline. A page that makes no network
calls once loaded still has to be *loadable*, and `/tools` was in neither
`PRECACHE` nor `RUNTIME_CACHEABLE` in `public/sw.js`. Offline it fell through
to the `/offline` shell. The calculators could not be reached at all, and both
proofs above stayed green the whole time.

## The trap found on the way to fixing it

The obvious fix — add `/tools` to `PRECACHE` — is worse than the bug, and a
real offline run is what showed it.

The page came back. The inputs did nothing. Every field sat at its default
(650000 / 12.5% / 84 months) and the result read **₹11,649** no matter what
was typed. React had not hydrated: its chunks live under `/_next/static/`,
which this worker deliberately does not cache, so the HTML was served from the
cache with nothing to bring it to life.

**A calculator that looks alive and is not is worse than an honest "you are
offline" page.** A farmer would read ₹11,649 as an answer to the numbers they
just entered.

So `/tools` is **runtime-cached, not precached**. That ties the cached copy to
a real visit — and the same visit is what puts the page's JS in the HTTP
cache, so a device only ever holds a copy it can actually run. `/mandi` and
`/saved` were already runtime-cached for a related reason; this is the third
case of the same rule.

## Why the proof is a script and not an e2e spec

The e2e harness runs `next dev`, which serves chunks as:

```
Cache-Control: no-store, must-revalidate
```

`no-store` forbids the browser from keeping them. Offline under `next dev`
there is nothing to hydrate from — every run reads ₹11,649, and no timeout,
selector or retry can reach past it. It is the dev server instructing the
browser, not a flake.

A production build serves those chunks immutable, so one real visit leaves
them in the HTTP cache and hydration survives the network going away. That is
a different build, so it gets a different run — the same reason the perf work
grew `scripts/perf-home.mjs` instead of trusting a dev-mode score.

The split is therefore deliberate:

| Proof | Where | What it establishes |
|---|---|---|
| `/tools` returns the real page offline, not the shell | `e2e/agri-pwa.spec.ts`, in CI | the worker caches and serves the route |
| the calculators **compute** offline | `scripts/verify-offline-tools.mjs`, prod build | the claim in AG-A12 |

## One more mechanism worth knowing

The first version of the production proof failed too, and correctly: offline,
it got the `/offline` shell.

A service worker caches only what its own `fetch` handler sees, and **the
first navigation of a session is served before the worker controls the page**.
That navigation is invisible to it and caches nothing. Runtime-cached means
"held after the visitor has actually been here while the worker was running",
so the proof now makes a second online visit before going offline.

That is not padding the test. It is the difference between a first-time
visitor — who correctly gets the shell — and a returning one, who gets the
calculators. Only the second is what AG-A12 claims.

## What is still not proven

- **A visitor who has never opened `/tools`** gets the `/offline` shell. That
  is the intended behaviour, not a gap, but it means "works offline" is true
  of returning visitors only.
- **Anything but Chromium.** The proof runs one engine.
- **The other three calculators.** EMI is the fixture; seed rate, fertiliser
  dose and spray dilution share the page, the bundle and the hydration path,
  so they stand or fall together — but only EMI has an asserted number.
