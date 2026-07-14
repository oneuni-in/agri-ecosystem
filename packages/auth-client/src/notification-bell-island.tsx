"use client";

/** Bell + unread badge wired to the notify BFF path (D12). Fetches once
 * after auth resolves and again on window focus - deliberately no polling
 * (the bell rides every page's header, which sits under the Lighthouse
 * home-page budget). */
import { NotificationBell } from "@agri/ui";
import { useEffect, useState } from "react";

import { useAgriUser } from "./react";

export function NotificationBellIsland({
  basePath,
  href,
  label,
}: {
  basePath: string;
  href: string;
  label: string;
}) {
  const { status } = useAgriUser({ autoSilentSso: false });
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (status !== "authenticated") return;
    let cancelled = false;
    const refresh = async () => {
      try {
        const res = await fetch(`${basePath}/unread-count`);
        if (!res.ok || cancelled) return;
        const body = (await res.json()) as { unread: number };
        if (!cancelled) setUnread(body.unread);
      } catch {
        /* badge is best-effort */
      }
    };
    void refresh();
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
    };
  }, [status, basePath]);

  if (status !== "authenticated") return null;
  return (
    <NotificationBell
      unread={unread}
      label={label}
      onClick={() => window.location.assign(href)}
    />
  );
}
