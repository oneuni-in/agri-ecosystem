"use client";

/** Bell for AgriID's own header strip (D12). web-id is the IdP itself, so
 * there's no useAgriUser here - the session cookie rides same-origin and a
 * 401 just means "not signed in", in which case the bell hides. */
import { NotificationBell } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const BASE = "/api/id/notify";

export function NotificationBellWidget() {
  const t = useTranslations("ui.notifications");
  const router = useRouter();
  const [unread, setUnread] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch(`${BASE}/unread-count`);
        if (cancelled) return;
        if (!res.ok) {
          setUnread(null);
          return;
        }
        const body = (await res.json()) as { unread: number };
        if (!cancelled) setUnread(body.unread);
      } catch {
        if (!cancelled) setUnread(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (unread === null) return null;
  return (
    <NotificationBell
      unread={unread}
      label={t("bell")}
      onClick={() => router.push("/notifications")}
    />
  );
}
