"use client";

import { NotificationsPanel, type NotificationItem, type NotificationsStrings } from "@agri/ui";

// Fixture data: one read, one unread — the stub `api` never round-trips.
const FIXTURES: NotificationItem[] = [
  {
    id: "n1",
    body: "Your PM-Kisan eKYC deadline is in 5 days.",
    created_at: "2026-07-10T09:00:00.000Z",
    read_at: null,
  },
  {
    id: "n2",
    body: "Mandi price alert: Tomato ₹2,340/q (+6%).",
    created_at: "2026-07-08T06:30:00.000Z",
    read_at: "2026-07-08T07:00:00.000Z",
  },
];

export function NotificationsPanelDemo({ strings }: { strings: NotificationsStrings }) {
  return (
    <NotificationsPanel
      api={{
        list: async () => ({ items: FIXTURES, next_cursor: null }),
        markRead: async () => {},
        markAllRead: async () => {},
      }}
      strings={strings}
    />
  );
}
