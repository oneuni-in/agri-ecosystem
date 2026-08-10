"use client";

/**
 * Client surface of @agri/auth-client (D10.C). Everything here works off the
 * /api/auth/* BFF routes - no token ever reaches this module.
 */
import { Avatar, Button } from "@agri/ui";
import { useCallback, useEffect, useState } from "react";

import { currentRelativeUrl, shouldAttemptSilentSso, SSO_MARKER } from "./react-helpers";
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
    void (async () => {
      try {
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
        if (shouldAttemptSilentSso(res.status, autoSilentSso, sessionStorage.getItem(SSO_MARKER))) {
          const next = encodeURIComponent(currentRelativeUrl(window.location));
          // Ask before navigating. Silent SSO is a TOP-LEVEL navigation (the
          // provider's session cookie is SameSite=Lax, so a cross-site fetch
          // would never carry it), which means an unreachable provider costs
          // this visitor a whole extra page load — or, worse, drops them on
          // the browser's error page. One cheap same-origin JSON call decides
          // whether the navigation is worth making at all.
          const probe = await fetch(`/api/auth/login?silent=1&probe=1&next=${next}`).catch(
            () => null,
          );
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
 * instead of adding a sibling; don't repeat that. */
export function AuthCluster({ loginLabel = "Login" }: { loginLabel?: string }) {
  const { user, status, login, logout } = useAgriUser();
  if (status === "loading") return null;
  if (user) {
    return (
      <Avatar
        initial={(user.name ?? user.agriId).charAt(0).toUpperCase()}
        title="Log out"
        onClick={() => void logout()}
      />
    );
  }
  return (
    <Button variant="brand" onClick={login}>
      {loginLabel}
    </Button>
  );
}
