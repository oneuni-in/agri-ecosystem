/**
 * One `beforeinstallprompt` capture for the whole app (D28).
 *
 * The event fires once per page load and only the FIRST `prompt()` on it is
 * honoured by Chrome, so two components each registering their own listener is
 * not a duplication smell — it is a bug: whichever mounted second would hold a
 * dead event and its button would do nothing. §10b's inline install band and
 * the fixed install banner both need it, so the capture lives here once and
 * both islands subscribe to the same snapshot.
 *
 * Registration is deferred to post-load idle for the reason `PwaClient`
 * already documented: install-prompt work during first paint cost measurable
 * Lighthouse perf on the audited home (CI floor 0.90). The trade is known and
 * accepted — an event that fires before idle is missed, and the iOS hint path
 * is unaffected because Safari never fires it at all.
 */

import { INSTALL_DISMISS_COOKIE, dismissalCookie, isDismissedIn } from "./dismissal";

export interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
}

export interface InstallSnapshot {
  /** A live, un-prompted `beforeinstallprompt` (Android/Chrome). */
  event: BeforeInstallPromptEvent | null;
  /** iOS Safari, which never fires the event: manual Add-to-Home-Screen. */
  ios: boolean;
  /** Already installed, or dismissed inside the last 30 days. */
  hidden: boolean;
}

let snapshot: InstallSnapshot = { event: null, ios: false, hidden: false };
let started = false;
const listeners = new Set<(next: InstallSnapshot) => void>();

function emit(next: InstallSnapshot): void {
  snapshot = next;
  for (const listener of listeners) listener(snapshot);
}

function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as { standalone?: boolean }).standalone === true
  );
}

function isDismissed(): boolean {
  // lib/dismissal.ts — U1 bans localStorage; `milk_a2hs` is the same flag the
  // fixed banner has always used, shared across every install surface.
  return isDismissedIn(document.cookie, INSTALL_DISMISS_COOKIE);
}

/**
 * Runs `fn` once the page has loaded and the main thread is idle. Shared with
 * `PwaClient`, which uses it for service-worker registration on the same
 * post-paint principle.
 */
export function afterLoadIdle(fn: () => void): () => void {
  const run = () => {
    const idle = (window as { requestIdleCallback?: typeof requestIdleCallback })
      .requestIdleCallback;
    if (idle) idle(fn, { timeout: 3000 });
    else setTimeout(fn, 1000);
  };
  if (document.readyState === "complete") {
    run();
    return () => {};
  }
  window.addEventListener("load", run, { once: true });
  return () => window.removeEventListener("load", run);
}

/**
 * Subscribes to the shared snapshot, starting the capture on first call.
 * Returns an unsubscribe. Safe to call from any number of islands.
 */
export function subscribeInstall(listener: (next: InstallSnapshot) => void): () => void {
  listeners.add(listener);
  listener(snapshot);
  if (!started) {
    started = true;
    afterLoadIdle(() => {
      if (isStandalone() || isDismissed()) {
        emit({ event: null, ios: false, hidden: true });
        return;
      }
      window.addEventListener("beforeinstallprompt", (event: Event) => {
        event.preventDefault(); // hold it behind our own UI
        emit({ ...snapshot, event: event as BeforeInstallPromptEvent });
      });
      if (/iPad|iPhone|iPod/.test(navigator.userAgent)) emit({ ...snapshot, ios: true });
    });
  }
  return () => {
    listeners.delete(listener);
  };
}

/** Fires the held prompt. Chrome consumes the event either way, so the
 * snapshot is cleared regardless of what the visitor chose. */
export async function promptInstall(): Promise<void> {
  const held = snapshot.event;
  if (!held) return;
  try {
    await held.prompt();
  } finally {
    emit({ event: null, ios: false, hidden: true });
  }
}

/** "Dismissed stays dismissed" for 30 days, across every install surface. */
export function dismissInstall(): void {
  document.cookie = dismissalCookie(INSTALL_DISMISS_COOKIE);
  emit({ event: null, ios: false, hidden: true });
}
