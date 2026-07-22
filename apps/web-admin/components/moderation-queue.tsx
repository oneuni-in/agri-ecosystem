"use client";

/**
 * D21 Task 14: the ONE moderation queue UI. Generic over `type_key` via the
 * unified /admin/moderation/* endpoints (Tasks 4-7) - approve/reject never
 * hit a per-domain endpoint. Replaces the forked claims-manager.tsx /
 * reviews-manager.tsx QueueSection copies (D22 gate: one queue, no
 * duplicates), keeping their card-list + Modal-confirmed decision + useToast
 * idiom. A 409 (raced decision - e.g. two moderators on the same item) is
 * treated like reviews-manager.tsx's precedent: drop the item with a soft
 * toast instead of an error toast, since the queue is merely stale.
 *
 * Media (claim evidence / verification docs / creative assets) is rendered
 * generically here rather than per-caller: the count is sniffed from the
 * payload's `evidence_count` / `doc_count` / `media_count` field, whichever
 * is present, so one strip implementation covers all three media-bearing
 * types instead of being copy-pasted per renderItem.
 */

import { Button, Card, EmptyState, Modal, Skeleton, useToast } from "@agri/ui";
import { useEffect, useState, type ReactNode } from "react";

import { ApiError, getJson, postJson } from "@/lib/api";

export interface ModItem {
  type_key: string;
  id: string;
  created_at: string;
  title: string;
  summary: string;
  payload: Record<string, unknown>;
}

function mediaCountFor(payload: Record<string, unknown>): number {
  const raw = payload.evidence_count ?? payload.doc_count ?? payload.media_count ?? 0;
  return typeof raw === "number" ? raw : 0;
}

function MediaStrip({
  item,
  count,
  mediaUrl,
}: {
  item: ModItem;
  count: number;
  mediaUrl: (item: ModItem, index: number) => string;
}) {
  if (count === 0) return null;
  return (
    <div className="flex gap-2 overflow-x-auto">
      {Array.from({ length: count }, (_, index) => (
        // eslint-disable-next-line @next/next/no-img-element -- auth-gated BFF stream (evidence/doc/media JPEG), not a static asset
        <img
          key={index}
          src={mediaUrl(item, index)}
          alt={`Media ${index + 1}`}
          className="h-24 w-24 shrink-0 rounded-card border border-line object-cover"
        />
      ))}
    </div>
  );
}

function DecideActions({
  busy,
  onApprove,
  onReject,
}: {
  busy: boolean;
  onApprove: (note: string) => void;
  onReject: (note: string) => void;
}) {
  const [note, setNote] = useState("");
  const trimmed = note.trim();
  const canReject = trimmed.length >= 1 && trimmed.length <= 500;
  return (
    <div className="space-y-2">
      <textarea
        className="min-h-[44px] w-full rounded-btn border border-line bg-card p-2 text-sm text-ink"
        placeholder="Note (optional on approve, required to reject)"
        value={note}
        maxLength={500}
        onChange={(event) => setNote(event.target.value)}
      />
      <div className="flex gap-2">
        <Button variant="brand" disabled={busy} onClick={() => onApprove(trimmed)}>
          Approve
        </Button>
        <Modal
          trigger={<Button disabled={busy}>Reject</Button>}
          title="Reject with this note?"
          description="The note is required (1-500 characters) and is shown as the rejection reason."
          closeLabel="Cancel"
        >
          <Button disabled={busy || !canReject} onClick={() => onReject(trimmed)}>
            Confirm reject
          </Button>
        </Modal>
      </div>
    </div>
  );
}

export function ModerationQueue({
  typeKey,
  renderItem,
  mediaUrl,
  onDecided,
}: {
  typeKey: string;
  renderItem: (item: ModItem) => ReactNode;
  mediaUrl?: ((item: ModItem, index: number) => string) | undefined;
  /** Fired after an item leaves the list - decided or 409-dropped - so the
   * caller can keep an out-of-band pending count (e.g. a tab chip) in sync
   * without this component needing to know anything about summaries. */
  onDecided?: ((typeKey: string) => void) | undefined;
}) {
  const { toast } = useToast();
  const [items, setItems] = useState<ModItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = async (cursor?: string) => {
    if (cursor) setLoadingMore(true);
    else setLoading(true);
    try {
      const params = new URLSearchParams({ type: typeKey, limit: "20" });
      if (cursor) params.set("cursor", cursor);
      const body = await getJson(`/moderation/queue?${params}`);
      const page = body.items as ModItem[];
      setItems((prev) => (cursor ? [...prev, ...page] : page));
      setNextCursor((body.next_cursor ?? null) as string | null);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : "Could not load the queue" });
    } finally {
      if (cursor) setLoadingMore(false);
      else setLoading(false);
    }
  };

  // One mount per typeKey - the caller remounts this component via key={typeKey}.
  useEffect(() => {
    void load();
  }, []);

  const loadMore = () => {
    if (loadingMore || !nextCursor) return; // D20 load-more lesson: guard the in-flight state
    void load(nextCursor);
  };

  const decide = async (item: ModItem, action: "approve" | "reject", note: string) => {
    setBusyId(item.id);
    try {
      const payload = note ? { note } : {};
      await postJson(`/moderation/${item.type_key}/${item.id}/${action}`, payload);
      setItems((prev) => prev.filter((existing) => existing.id !== item.id));
      onDecided?.(item.type_key);
      toast({ title: action === "approve" ? "Approved" : "Rejected" });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setItems((prev) => prev.filter((existing) => existing.id !== item.id));
        onDecided?.(item.type_key);
        toast({ title: "Already decided elsewhere - removed from queue" });
      } else {
        toast({ title: error instanceof ApiError ? error.detail : "Decision failed" });
      }
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card className="space-y-3 p-4">
      {loading && items.length === 0 ? (
        <div className="space-y-2">
          <Skeleton width="100%" height="96px" />
          <Skeleton width="100%" height="96px" />
        </div>
      ) : null}
      {!loading && items.length === 0 ? <EmptyState icon="🗂️" title="Nothing pending" /> : null}
      <ul className="space-y-3">
        {items.map((item) => {
          const count = mediaUrl ? mediaCountFor(item.payload) : 0;
          return (
            <li key={item.id}>
              <Card className="space-y-3 p-3">
                {renderItem(item)}
                {mediaUrl ? <MediaStrip item={item} count={count} mediaUrl={mediaUrl} /> : null}
                <p className="text-xs text-sub">{new Date(item.created_at).toLocaleString()}</p>
                <DecideActions
                  busy={busyId === item.id}
                  onApprove={(note) => void decide(item, "approve", note)}
                  onReject={(note) => void decide(item, "reject", note)}
                />
              </Card>
            </li>
          );
        })}
      </ul>
      {nextCursor ? (
        <Button disabled={loadingMore} onClick={loadMore}>
          {loadingMore ? "Loading…" : "Load more"}
        </Button>
      ) : null}
    </Card>
  );
}
