/* Milk.in service worker (D28). Hand-rolled: the cache policy IS the threat
 * model — /api/* is never intercepted (no PII in caches), only same-origin
 * GETs are handled, navigations are network-first with an /offline shell
 * fallback, and hashed _next/static assets are cache-first. */
const VERSION = "v2"; // bump to invalidate all caches
const SHELL_CACHE = `milk-shell-${VERSION}`;
const ASSET_CACHE = `milk-assets-${VERSION}`;
const OFFLINE_URL = "/offline";
const PRECACHE = [OFFLINE_URL, "/manifest.webmanifest", "/icons/icon-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(PRECACHE))
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
            .filter((key) => key !== SHELL_CACHE && key !== ASSET_CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return; // NEVER cache API responses (PII rule)

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() =>
        caches.match(OFFLINE_URL).then((hit) => hit ?? Response.error()),
      ),
    );
    return;
  }
  // NOTE: /_next/static/* is deliberately NOT SW-cached. In production the
  // browser HTTP cache already holds those (immutable cache-control); in dev
  // the URLs are NOT content-hashed, and a cache-first SW serves stale
  // modules after Fast Refresh recompiles — which triggers full page
  // reloads that abort in-flight fetches (broke three e2e specs).
  if (url.pathname.startsWith("/icons/")) {
    event.respondWith(
      caches.match(event.request).then(
        (hit) =>
          hit ??
          fetch(event.request).then((res) => {
            if (res.ok) {
              const copy = res.clone();
              caches.open(ASSET_CACHE).then((cache) => cache.put(event.request, copy));
            }
            return res;
          }),
      ),
    );
  }
});

self.addEventListener("push", (event) => {
  let data = { title: "Milk.in", body: "", url: "/notifications" };
  try {
    data = { ...data, ...event.data.json() };
  } catch {
    /* payload-less push: show the generic notification */
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      data: { url: data.url },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/notifications";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      const win = wins.find((w) => "focus" in w);
      return win ? win.focus().then(() => win.navigate(url)) : self.clients.openWindow(url);
    }),
  );
});
