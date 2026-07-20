"use client";

/**
 * D18 Task 13: admin review moderation queue. Forked from
 * claims-manager.tsx's QueueSection idiom (card-list + Modal-confirmed
 * decision + useToast) but single-queue and review-shaped: each card shows
 * RatingStars + the first non-empty locale body + a target-type chip. A 409
 * (already_decided - e.g. two moderators racing the same review) is treated
 * like a successful decision: the item drops out of the list with a
 * "already decided" toast rather than an error toast, since the queue is
 * simply stale, not broken.
 */

import { Button, Card, EmptyState, Modal, RatingStars, Skeleton, useToast } from "@agri/ui";
import { useEffect, useState } from "react";

import { ApiError, getJson, postJson } from "@/lib/api";

interface ReviewBody {
  en?: string;
  ta?: string;
  hi?: string;
}

interface AdminReview {
  id: string;
  author_user_id: string;
  target_type: string;
  target_id: string;
  rating: number;
  body: ReviewBody | null;
  moderation_status: string;
  created_at: string;
}

function bodyText(body: ReviewBody | null): string {
  if (!body) return "—";
  return body.en?.trim() || body.ta?.trim() || body.hi?.trim() || "—";
}

/** Badge's variant union (sponsored/verified/cert) is fixed marketing
 * semantics with fixed palettes - it doesn't model an open-ended
 * target_type string, so it renders as a plain token-styled pill instead
 * (same idiom as users-manager.tsx's StatusPill). */
function TargetChip({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center self-start rounded-pill border border-line bg-ghost px-[9px] py-[3px] text-[11px] font-extrabold text-ink">
      {label}
    </span>
  );
}

function DecideActions({
  busy,
  onApprove,
  onReject,
}: {
  busy: boolean;
  onApprove: () => void;
  onReject: (note: string) => void;
}) {
  const [note, setNote] = useState("");
  const canReject = note.trim().length >= 3;
  return (
    <div className="space-y-2">
      <textarea
        className="min-h-[44px] w-full rounded-btn border border-line bg-card p-2 text-sm text-ink"
        placeholder="Rejection note (required, min 3 characters)"
        value={note}
        onChange={(event) => setNote(event.target.value)}
      />
      <div className="flex gap-2">
        <Modal
          trigger={
            <Button variant="brand" disabled={busy}>
              Approve
            </Button>
          }
          title="Approve this review?"
          description="It becomes visible on the public listing."
          closeLabel="Cancel"
        >
          <Button variant="brand" disabled={busy} onClick={onApprove}>
            Confirm approve
          </Button>
        </Modal>
        <Modal
          trigger={<Button disabled={busy}>Reject</Button>}
          title="Reject with this note?"
          description="The note explains why the review was rejected."
          closeLabel="Cancel"
        >
          <Button disabled={busy || !canReject} onClick={() => onReject(note)}>
            Confirm reject
          </Button>
        </Modal>
      </div>
    </div>
  );
}

export function ReviewsManager() {
  const { toast } = useToast();
  const [items, setItems] = useState<AdminReview[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = async (cursor?: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "20", status: "pending" });
      if (cursor) params.set("cursor", cursor);
      const body = await getJson(`/reviews?${params}`);
      const page = body.items as AdminReview[];
      setItems((prev) => (cursor ? [...prev, ...page] : page));
      setNextCursor((body.next_cursor ?? null) as string | null);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : "Could not load reviews" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const decide = async (item: AdminReview, action: "approve" | "reject", note?: string) => {
    setBusyId(item.id);
    try {
      await postJson(`/reviews/${item.id}/${action}`, action === "reject" ? { note } : undefined);
      setItems((prev) => prev.filter((existing) => existing.id !== item.id));
      toast({ title: action === "approve" ? "Approved" : "Rejected" });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setItems((prev) => prev.filter((existing) => existing.id !== item.id));
        toast({ title: "Already decided by someone else - removed from queue" });
      } else {
        toast({ title: error instanceof ApiError ? error.detail : "Decision failed" });
      }
    } finally {
      setBusyId(null);
    }
  };

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-4">
      <h1 className="text-xl font-bold text-ink">Review moderation</h1>
      <Card className="space-y-3 p-4">
        <h2 className="font-display text-lg font-extrabold text-ink">Pending reviews</h2>
        {loading && items.length === 0 ? (
          <div className="space-y-2">
            <Skeleton width="100%" height="96px" />
            <Skeleton width="100%" height="96px" />
          </div>
        ) : null}
        {!loading && items.length === 0 ? (
          <EmptyState icon="⭐" title="No pending reviews" />
        ) : null}
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.id}>
              <Card className="space-y-3 p-3">
                <div className="flex items-center justify-between gap-2">
                  <RatingStars value={item.rating} />
                  <TargetChip label={item.target_type} />
                </div>
                <p className="text-sm text-ink">{bodyText(item.body)}</p>
                <p className="text-xs text-sub">
                  by {item.author_user_id} · {new Date(item.created_at).toLocaleString()}
                </p>
                <DecideActions
                  busy={busyId === item.id}
                  onApprove={() => void decide(item, "approve")}
                  onReject={(note) => void decide(item, "reject", note.trim())}
                />
              </Card>
            </li>
          ))}
        </ul>
        {nextCursor ? <Button onClick={() => void load(nextCursor)}>Load more</Button> : null}
      </Card>
    </main>
  );
}
