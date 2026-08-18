/* Agri.in service worker — A-U4 W4 (was A-U3 W2's single-purpose worker).
 *
 * ONE worker, extended in place. A-U3 shipped this for /helplines alone and
 * said the PWA sweep would extend it rather than register a second one; this
 * is that extension. A second registration is the failure mode to avoid —
 * two workers on one scope fight over fetch handling and the loser's cache
 * silently goes stale.
 *
 * WHAT IS CACHED, AND WHY EACH ONE EARNS IT. Every entry here is a page where
 * a stale answer beats no answer for someone with no signal:
 *
 *   /helplines  — a farmer who needs the Kisan Call Centre is often exactly
 *                 the farmer with no bars. `tel:` needs no network once the
 *                 page is on screen. (A-U3; unchanged.)
 *   /mandi      — last-known prices. A price from this morning is worth a
 *                 great deal at a mandi gate with no signal; no price at all
 *                 is worth nothing. The stamp on the page carries its own
 *                 as-of date, so a stale page still says how stale it is.
 *   /saved      — items the visitor deliberately saved to read later, which
 *                 is close to a declaration that they expect to read them
 *                 somewhere without signal.
 *   /offline    — the shell, shown for any OTHER navigation that fails.
 *
 * Cache policy IS the threat model (milk's D28 sw.js, same rules):
 *  - only same-origin GETs are touched at all;
 *  - /api/* is NEVER intercepted — no PII in caches, ever. This matters more
 *    now than it did in A-U3: /saved is per-user, so its API payload must
 *    never land in a shared cache. Only the RENDERED page is cached, by the
 *    browser that rendered it, and a logged-out visitor re-fetches it.
 *  - /_next/static/* is deliberately NOT cached. Production sets immutable
 *    cache-control so the browser already holds it, and in dev those URLs
 *    are not content-hashed — a cache-first SW then serves stale modules
 *    after Fast Refresh, which forces reloads that abort in-flight fetches
 *    (this broke three milk e2e specs; do not "fix" it by adding them here).
 */
const VERSION = "v2"; // bumped by A-U4 W4 — invalidates A-U3's v1 caches
const CACHE = `agri-offline-${VERSION}`;

/** Precached at install. /offline must be here or the shell cannot show. */
const PRECACHE = ["/offline", "/helplines"];

/** Navigations kept fresh in the cache as the visitor uses them. Not
 * precached: /saved is per-user and /mandi is large, so both are stored only
 * once the visitor has actually been there. */
const RUNTIME_CACHEABLE = new Set(["/helplines", "/mandi", "/saved"]);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      // Failing to precache must not wedge the install: the pages still work
      // online, and the next visit retries.
      .catch(() => undefined)
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return; // NEVER cache API responses
  if (event.request.mode !== "navigate") return; // documents only

  const cacheable = RUNTIME_CACHEABLE.has(url.pathname);

  event.respondWith(
    // Network first, always. These pages carry dates and prices, so a fresh
    // answer is strictly better when one is available; the cache is the
    // fallback, never the default.
    fetch(event.request)
      .then((response) => {
        if (cacheable && response.ok) {
          const copy = response.clone();
          void caches.open(CACHE).then((cache) => cache.put(url.pathname, copy));
        }
        return response;
      })
      .catch(async () => {
        const cache = await caches.open(CACHE);
        // The page itself if we have it; otherwise the shell, which explains
        // what is happening and links to what IS cached.
        return (await cache.match(url.pathname)) ?? (await cache.match("/offline")) ?? Response.error();
      }),
  );
});
