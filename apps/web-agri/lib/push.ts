/**
 * A-U4 W3 — web-push subscription for agri.in.
 *
 * PORTED VERBATIM from apps/web-milk/lib/push.ts, whose flow is already
 * proven end-to-end (D28, verified 2026-08-04). The one rule that makes this
 * a port rather than a rewrite: a failed server call unsubscribes the browser
 * again, so the browser is never left holding a subscription the backend has
 * never heard of. Two independent implementations of that would drift, and
 * the drift shows up as orphaned endpoints nobody can send to.
 *
 * The push CHANNEL PREFERENCE is a server-side D12 setting
 * (PUT /notify/preferences); this module owns THIS DEVICE's subscription only.
 *
 * agri.in already registers a service worker (A-U3's offline helplines page,
 * /sw.js) — this reuses that ONE registration rather than adding a second,
 * which W4's PWA pass also depends on.
 */
const VAPID = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? "";

/** No key provisioned → the feature stays dark rather than offering a button
 * that cannot work. Production sets this at BUILD time (see the launch
 * blockers note): it is inlined, not read at runtime. */
export const PUSH_CONFIGURED = VAPID !== "";

export type PushState = "unsupported" | "ios-install" | "idle" | "subscribed" | "denied";

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

/** What this device can do right now. Never throws — an unknown environment
 * resolves to "unsupported", which every caller renders as nothing. */
export async function detectPushState(): Promise<PushState> {
  if (!PUSH_CONFIGURED) return "unsupported";
  if (!("serviceWorker" in navigator)) return "unsupported";
  if (!("PushManager" in window)) {
    // iOS Safari exposes PushManager only inside an installed PWA (16.4+).
    return /iPad|iPhone|iPod/.test(navigator.userAgent) ? "ios-install" : "unsupported";
  }
  if (Notification.permission === "denied") return "denied";
  try {
    const registration = await navigator.serviceWorker.ready;
    return (await registration.pushManager.getSubscription()) ? "subscribed" : "idle";
  } catch {
    return "unsupported";
  }
}

/** Asks for permission, subscribes, and registers the endpoint server-side.
 * A failed server call unsubscribes again so the browser is never left holding
 * a subscription the backend has never heard of. */
export async function subscribePush(): Promise<PushState> {
  const registration = await navigator.serviceWorker.ready;
  if ((await Notification.requestPermission()) !== "granted") return "denied";
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(VAPID) as BufferSource,
  });
  const json = subscription.toJSON();
  const res = await fetch("/api/notify/push/subscriptions", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      endpoint: json.endpoint,
      keys: { p256dh: json.keys?.p256dh, auth: json.keys?.auth },
    }),
  });
  if (res.ok) return "subscribed";
  await subscription.unsubscribe();
  return "idle";
}

export async function unsubscribePush(): Promise<PushState> {
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (subscription) {
    await fetch("/api/notify/push/subscriptions", {
      method: "DELETE",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ endpoint: subscription.endpoint }),
    });
    await subscription.unsubscribe();
  }
  return "idle";
}
