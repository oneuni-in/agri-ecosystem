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
          sessionStorage.setItem(SSO_MARKER, "1");
          window.location.assign(
            `/api/auth/login?silent=1&next=${encodeURIComponent(currentRelativeUrl(window.location))}`,
          );
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
 * longer renders one itself (its `coinsBalance` field was a D10 placeholder,
 * always 0, now superseded). Drop into HeaderStack's `right` slot. */
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
