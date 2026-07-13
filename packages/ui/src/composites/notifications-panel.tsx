"use client";

/**
 * Notification center list (D12): cursor "load more", per-row + bulk
 * mark-read. Data access is injected so web-id (cookie rewrite) and the
 * public apps (bearer BFF proxy) reuse one component.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "../components/button";
import { Card } from "../components/card";
import { EmptyState } from "../components/empty-state";
import { Skeleton } from "../components/skeleton";
import { cn } from "../lib/cn";

export interface NotificationItem {
  id: string;
  body: string;
  created_at: string;
  read_at: string | null;
}

export interface NotificationsApi {
  list: (cursor?: string) => Promise<{ items: NotificationItem[]; next_cursor: string | null }>;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
}

export interface NotificationsStrings {
  title: string;
  empty: string;
  markAllRead: string;
  markRead: string;
  loadMore: string;
}

export function NotificationsPanel({
  api,
  strings,
}: {
  /** May be a new object identity on every render — do not put it in a dep array. */
  api: NotificationsApi;
  strings: NotificationsStrings;
}) {
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const apiRef = useRef(api);
  useEffect(() => {
    apiRef.current = api;
  });

  const load = useCallback(async (after?: string) => {
    const page = await apiRef.current.list(after);
    setItems((prev) => (after && prev ? [...prev, ...page.items] : page.items));
    setCursor(page.next_cursor);
  }, []);

  useEffect(() => {
    void load().catch(() => setItems([]));
  }, [load]);

  const markRead = useCallback(async (id: string) => {
    await apiRef.current.markRead(id);
    setItems((prev) =>
      prev
        ? prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n))
        : prev,
    );
  }, []);

  const markAllRead = useCallback(async () => {
    setBusy(true);
    try {
      await apiRef.current.markAllRead();
      const stamp = new Date().toISOString();
      setItems((prev) => (prev ? prev.map((n) => ({ ...n, read_at: n.read_at ?? stamp })) : prev));
    } finally {
      setBusy(false);
    }
  }, []);

  if (items === null) {
    return (
      <div className="grid gap-2" data-testid="notifications-loading">
        <Skeleton width="100%" height="64px" />
        <Skeleton width="100%" height="64px" />
        <Skeleton width="100%" height="64px" />
      </div>
    );
  }
  if (items.length === 0) {
    return <EmptyState icon="🔔" title={strings.title} description={strings.empty} />;
  }
  return (
    <section aria-label={strings.title}>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-display text-[18px] font-extrabold text-ink">{strings.title}</h2>
        <Button
          variant="ghost"
          className="flex-none"
          disabled={busy}
          onClick={() => void markAllRead()}
        >
          {strings.markAllRead}
        </Button>
      </div>
      <ul className="grid gap-2" data-testid="notification-list">
        {items.map((item) => (
          <li key={item.id}>
            <Card className={cn("flex items-start justify-between gap-3 p-4")}>
              <div>
                <p className={cn("text-[14px]", item.read_at ? "text-sub" : "font-bold text-ink")}>
                  {item.body}
                </p>
                <time className="text-[12px] text-sub" dateTime={item.created_at}>
                  {new Date(item.created_at).toLocaleString()}
                </time>
              </div>
              {item.read_at === null ? (
                <Button variant="ghost" className="flex-none" onClick={() => void markRead(item.id)}>
                  {strings.markRead}
                </Button>
              ) : null}
            </Card>
          </li>
        ))}
      </ul>
      {cursor ? (
        <div className="mt-3 flex justify-center">
          <Button variant="ghost" className="flex-none" onClick={() => void load(cursor)}>
            {strings.loadMore}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
