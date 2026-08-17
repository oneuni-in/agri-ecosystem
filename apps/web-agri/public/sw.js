/* Agri.in service worker — SINGLE PURPOSE (A-U3 W2).
 *
 * This is NOT the PWA sweep. That is A-U4, and it is deliberately not
 * happening here: there is no manifest, no install prompt, no push
 * handler, no offline shell for the whole site. This worker exists for
 * exactly one page.
 *
 * /helplines has to work with the network off. A farmer who needs the
 * Kisan Call Centre number is often precisely the farmer with no signal,
 * and `tel:` needs no network once the page is on screen. So the page is
 * precached at install and served cache-first — the only route in this
 * file with that policy, because it is the only one where a stale-but-
 * present answer beats a fresh-but-absent one.
 *
 * Cache policy IS the threat model (milk's D28 sw.js, same rules):
 *  - only same-origin GETs are touched at all;
 *  - /api/* is NEVER intercepted — no PII in caches, ever;
 *  - /_next/static/* is deliberately NOT cached. Production sets
 *    immutable cache-control so the browser already holds it, and in dev
 *    those URLs are not content-hashed — a cache-first SW then serves
 *    stale modules after Fast Refresh, which forces reloads that abort
 *    in-flight fetches (this broke three milk e2e specs; do not "fix"
 *    it by adding them here).
 */
const VERSION = "v1"; // bump to invalidate
const HELPLINE_CACHE = `agri-helplines-${VERSION}`;
const HELPLINE_URL = "/helplines";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(HELPLINE_CACHE)
      .then((cache) => cache.add(HELPLINE_URL))
      // Failing to precache must not wedge the install: the page still
      // works online, and the next visit retries.
      .catch(() => undefined)
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== HELPLINE_CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin)
    return;
  if (url.pathname.startsWith("/api/")) return; // NEVER cache API responses

  // Only /helplines. Every other navigation is left entirely alone —
  // this worker has no opinion about the rest of the site, which is what
  // keeps it out of A-U4's way.
  if (event.request.mode !== "navigate" || url.pathname !== HELPLINE_URL)
    return;

  event.respondWith(
    // Network first so a re-verified number reaches people, cache second
    // so a dead network still hands over a phone number.
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches
            .open(HELPLINE_CACHE)
            .then((cache) => cache.put(HELPLINE_URL, copy));
        }
        return response;
      })
      .catch(() =>
        caches.match(HELPLINE_URL).then((hit) => hit ?? Response.error()),
      ),
  );
});
