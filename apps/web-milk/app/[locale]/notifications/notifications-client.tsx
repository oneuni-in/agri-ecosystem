"use client";

import { NotificationsPanel, type NotificationsApi } from "@agri/ui";
import { useLocale, useTranslations } from "next-intl";
import { useMemo } from "react";

const BASE = "/api/notify";

async function ok(res: Response): Promise<void> {
  if (!res.ok) throw new Error(String(res.status));
}

export function NotificationsClient() {
  const t = useTranslations("ui.notifications");
  const locale = useLocale();
  const api = useMemo<NotificationsApi>(
    () => ({
      list: async (cursor) => {
        const params = new URLSearchParams({ locale });
        if (cursor) params.set("cursor", cursor);
        const res = await fetch(`${BASE}/notifications?${params}`);
        await ok(res);
        return (await res.json()) as Awaited<ReturnType<NotificationsApi["list"]>>;
      },
      markRead: async (id) => ok(await fetch(`${BASE}/notifications/${id}/read`, { method: "POST" })),
      markAllRead: async () => ok(await fetch(`${BASE}/notifications/read-all`, { method: "POST" })),
    }),
    [locale],
  );
  return (
    <NotificationsPanel
      api={api}
      strings={{
        title: t("title"),
        empty: t("empty"),
        markAllRead: t("markAllRead"),
        markRead: t("markRead"),
        loadMore: t("loadMore"),
      }}
    />
  );
}
