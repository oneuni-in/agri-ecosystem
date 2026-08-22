"use client";

/**
 * Client surface of @agri/auth-client (D10.C). Everything here works off the
 * /api/auth/* BFF routes - no token ever reaches this module.
 */
import { Avatar, AvatarMenu, AvatarMenuItem, Button } from "@agri/ui";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import { currentRelativeUrl, hasSessionHint, shouldAttemptSilentSso, SSO_MARKER } from "./react-helpers";
import type { AgriUser } from "./session";

export { NotificationBellIsland } from "./notification-bell-island";

export type AgriUserStatus = "loading" | "authenticated" | "unauthenticated";

export interface UseAgriUserResult {
  user: AgriUser | null;
  status: AgriUserStatus;
  login: () => void;
  logout: () => Promise<void>;
}

export function useAgriUser({ autoSilentSso = true }: { autoSilentSso?: boolean } = {}): UseAgriUserResult {
  const [user, setUser] = useState<AgriUser | null>(null);
  const [status, setStatus] = useState<AgriUserStatus>("loading");

  useEffect(() => {
    let cancelled = false;

    // Ask before navigating. Silent SSO is a TOP-LEVEL navigation (the
    // provider's session cookie is SameSite=Lax, so a cross-site fetch
    // would never carry it), which means an unreachable provider costs
    // this visitor a whole extra page load — or, worse, drops them on
    // the browser's error page. One cheap same-origin JSON call decides
    // whether the navigation is worth making at all.
    const attemptSilentSso = async (): Promise<void> => {
      const next = encodeURIComponent(currentRelativeUrl(window.location));
      const probe = await fetch(`/api/auth/login?silent=1&probe=1&next=${next}`).catch(() => null);
      if (cancelled) return;
      const reachable =
        probe?.ok === true &&
        ((await probe.json().catch(() => null)) as { reachable?: boolean } | null)?.reachable ===
          true;
      if (cancelled) return;
      if (!reachable) {
        setStatus("unauthenticated");
        return;
      }
      sessionStorage.setItem(SSO_MARKER, "1");
      window.location.assign(`/api/auth/login?silent=1&next=${next}`);
    };

    void (async () => {
      try {
        // No hint cookie = no session at this app (U4 A1): /api/auth/me could
        // only answer 401, and probing it logs a console error on every guest
        // page view. Treat the absence as the known 401 it is and go straight
        // to the silent-SSO decision — which must still run, because a
        // cross-app session (signed in on agri.in, first visit here) has no
        // local cookie either, and silent SSO is how it becomes one.
        if (!hasSessionHint(document.cookie)) {
          if (shouldAttemptSilentSso(401, autoSilentSso, sessionStorage.getItem(SSO_MARKER))) {
            await attemptSilentSso();
            return;
          }
          setStatus("unauthenticated");
          return;
        }
        const res = await fetch("/api/auth/me");
        if (cancelled) return;
        if (res.ok) {
          const body = (await res.json()) as { user: AgriUser };
          if (cancelled) return;
          sessionStorage.removeItem(SSO_MARKER);
          setUser(body.user);
          setStatus("authenticated");
          return;
        }
        // A 401 despite the hint means the hint was stale — the response has
        // just cleared both cookies (handleMe), so this happens once, and
        // silent SSO may still recover a live provider session.
        if (shouldAttemptSilentSso(res.status, autoSilentSso, sessionStorage.getItem(SSO_MARKER))) {
          await attemptSilentSso();
          return;
        }
        setStatus("unauthenticated");
      } catch {
        if (!cancelled) setStatus("unauthenticated");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [autoSilentSso]);

  const login = useCallback(() => {
    window.location.assign(
      `/api/auth/login?next=${encodeURIComponent(currentRelativeUrl(window.location))}`,
    );
  }, []);

  const logout = useCallback(async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    // suppress the automatic silent re-login this tab would otherwise do
    sessionStorage.setItem(SSO_MARKER, "1");
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  return { user, status, login, logout };
}

/**
 * Renders children only when a session hint is present (U4 A1): the gate for
 * header widgets that fetch AUTHENTICATED endpoints on mount but do not need
 * the full `useAgriUser` state machine — CoinsBalancePill is the canonical
 * case (it lives in @agri/ui, which cannot depend on this package). Without
 * the gate, every guest page view logs the widget's 401 as a console error.
 * SSR renders nothing, exactly like the gated widgets' own pre-fetch state,
 * so the gate adds no layout shift they weren't already paying.
 */
export function SignedIn({ children }: { children: ReactNode }) {
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    setSignedIn(hasSessionHint(document.cookie));
  }, []);
  if (!signedIn) return null;
  return <>{children}</>;
}

/** Right-side header cluster per the design system: avatar when authed,
 * Login button otherwise. The coins pill is D13's live CoinsBalancePill,
 * placed by each app's own header next to this cluster - AuthCluster no
 * longer renders one itself (its balance field on AgriUser was a D10
 * placeholder, always 0, now superseded and removed). Drop into
 * HeaderStack's `right` slot.
 *
 * THIS IS THE HEADER INTEGRATION POINT (D14 A4): future header widgets
 * (badges, alerts, balances, whatever) belong as SIBLINGS of <AuthCluster/>
 * in the `right` slot, the way CoinsBalancePill does - never render them
 * FROM INSIDE this component. Two D13 bugs (a duplicate coins pill, then a
 * dead placeholder field) both came from a spec reaching into AuthCluster
 * instead of adding a sibling; don't repeat that.
 *
 * THE AVATAR IS A MENU when `accountHref` is given. It used to BE the logout
 * button: tapping your own face signed you out, with no confirmation and no
 * other route to your account - and the A1 reference labels that same
 * element "Account". Passing `accountHref` turns it into Account + Log out,
 * and `photoSrc` lets an uploaded profile photo actually appear instead of
 * an initial.
 *
 * Both are OPTIONAL, and without them this renders exactly what it always
 * did. That is deliberate: three apps mount this cluster, and each needs its
 * own account route and its own proxy path for the photo - web-admin has no
 * account page at all. An app opts in by passing them. */
export function AuthCluster({
  loginLabel = "Login",
  accountHref,
  accountLabel = "Account",
  logoutLabel = "Log out",
  photoSrc,
}: {
  loginLabel?: string;
  /** Where "Account" goes. Omitted => the avatar keeps its old
   * logout-on-click behaviour rather than opening a menu with one item. */
  accountHref?: string;
  accountLabel?: string;
  logoutLabel?: string;
  /** Owner-scoped avatar endpoint, e.g. the app's `/api/identity/profile/avatar`
   * proxy. 404 (no photo uploaded) falls back to the initial. */
  photoSrc?: string;
}) {
  const { user, status, login, logout } = useAgriUser();
  if (status === "loading") return null;
  if (user) {
    const initial = (user.name ?? user.agriId).charAt(0).toUpperCase();
    if (accountHref) {
      return (
        <AvatarMenu initial={initial} photoSrc={photoSrc} label={accountLabel}>
          <AvatarMenuItem href={accountHref} icon="👤">
            {accountLabel}
          </AvatarMenuItem>
          <AvatarMenuItem onSelect={() => void logout()} icon="↪️">
            {logoutLabel}
          </AvatarMenuItem>
        </AvatarMenu>
      );
    }
    return (
      <Avatar initial={initial} title={logoutLabel} onClick={() => void logout()} />
    );
  }
  // `data-testid` because the label is translated: e2e's "wait for the header
  // to settle" helper matched /^login$/i and could therefore never settle on
  // /ta or /hi, where the button reads "உள்நுழை" / "लॉगिन".
  return (
    <Button variant="brand" onClick={login} data-testid="auth-login">
      {loginLabel}
    </Button>
  );
}
