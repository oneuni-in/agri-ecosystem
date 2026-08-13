"use client";

/**
 * Cursor-paginated list state for the U3 admin read surfaces. Every admin list
 * endpoint returns `{ items, next_cursor }` (the ecosystem-wide keyset shape),
 * so one hook feeds every `AdminDataTable`: it tracks items/cursor and its own
 * loading / error / load-more, reloading whenever `path` changes (filter
 * edits) and appending on load-more. `path` is the endpoint minus the cursor
 * param; the hook adds `?cursor=` / `&cursor=` itself.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, getJson } from "@/lib/api";

interface Page<T> {
  items?: T[];
  next_cursor?: string | null;
}

export function useAdminList<T>(path: string) {
  const [items, setItems] = useState<T[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);
  // The most recent request wins — a stale filter's response must not land.
  const reqId = useRef(0);

  const load = useCallback(
    async (next?: string) => {
      const first = !next;
      const mine = ++reqId.current;
      if (first) setLoading(true);
      else setLoadingMore(true);
      setError(undefined);
      try {
        const sep = path.includes("?") ? "&" : "?";
        const body = (await getJson(next ? `${path}${sep}cursor=${encodeURIComponent(next)}` : path)) as Page<T>;
        if (mine !== reqId.current) return; // superseded
        const page = body.items ?? [];
        setItems((current) => (first ? page : [...current, ...page]));
        setCursor((body.next_cursor ?? null) as string | null);
      } catch (e) {
        if (mine !== reqId.current) return;
        setError(e instanceof ApiError ? e.detail : "request_failed");
      } finally {
        if (mine === reqId.current) {
          if (first) setLoading(false);
          else setLoadingMore(false);
        }
      }
    },
    [path],
  );

  useEffect(() => {
    void load();
  }, [load]);

  return { items, cursor, loading, loadingMore, error, reload: load, setItems };
}
