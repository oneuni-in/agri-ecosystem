"use client";

/**
 * D16 Task 12: admin claim + verification queues. Two independent
 * pending-status queues (claims on seeded/unclaimed businesses, and
 * owner-requested verification-lite docs) sharing one generic QueueSection -
 * same card-list + Modal-confirmed decision + useToast idiom as
 * coins-admin.tsx's AbuseSection. Decisions are permanent (no unclaim /
 * unverify path), so a successful decide() simply drops the item from the
 * list rather than re-fetching it.
 */

import { Button, Card, EmptyState, Modal, Skeleton, useToast } from "@agri/ui";
import { useEffect, useState } from "react";

import { ApiError, getJson, postJson } from "@/lib/api";

interface AdminClaim {
  id: string;
  business_id: string;
  business_name: string;
  claimant_user_id: string;
  status: string;
  evidence_count: number;
  decision_note: string | null;
  created_at: string;
  decided_at: string | null;
}

interface AdminVerification {
  id: string;
  business_id: string;
  business_name: string;
  method: string;
  status: string;
  notes: string | null;
  doc_count: number;
  created_at: string;
  decided_at: string | null;
}

function EvidenceStrip({ base, count }: { base: string; count: number }) {
  if (count === 0) return null;
  return (
    <div className="flex gap-2 overflow-x-auto">
      {Array.from({ length: count }, (_, index) => (
        // eslint-disable-next-line @next/next/no-img-element -- auth-gated BFF stream (evidence JPEG), not a static asset
        <img
          key={index}
          src={`${base}/${index}`}
          alt={`Evidence ${index + 1}`}
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
  const canReject = note.trim().length >= 3;
  return (
    <div className="space-y-2">
      <textarea
        className="min-h-[44px] w-full rounded-btn border border-line bg-card p-2 text-sm text-ink"
        placeholder="Decision note (required to reject, min 3 characters)"
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
          title="Approve this?"
          description="This is permanent - there is no unclaim or unverify path."
          closeLabel="Cancel"
        >
          <Button variant="brand" disabled={busy} onClick={() => onApprove(note)}>
            Confirm approve
          </Button>
        </Modal>
        <Modal
          trigger={<Button disabled={busy}>Reject</Button>}
          title="Reject with this note?"
          description="The note is shown to the requester as the rejection reason."
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

function QueueSection<T extends { id: string }>({
  title,
  emptyIcon,
  emptyTitle,
  listPath,
  evidenceBase,
  evidenceCount,
  decidePath,
  line,
}: {
  title: string;
  emptyIcon: string;
  emptyTitle: string;
  listPath: string;
  evidenceBase: (item: T) => string;
  evidenceCount: (item: T) => number;
  decidePath: (item: T) => string;
  line: (item: T) => string;
}) {
  const { toast } = useToast();
  const [items, setItems] = useState<T[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = async (cursor?: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "20", status: "pending" });
      if (cursor) params.set("cursor", cursor);
      const body = await getJson(`${listPath}?${params}`);
      const page = body.items as T[];
      setItems(cursor ? [...items, ...page] : page);
      setNextCursor((body.next_cursor ?? null) as string | null);
    } catch {
      toast({ title: `Could not load ${title.toLowerCase()}` });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const decide = async (item: T, action: "approve" | "reject", note: string) => {
    setBusyId(item.id);
    try {
      await postJson(`${decidePath(item)}/${action}`, note.trim() ? { note: note.trim() } : {});
      setItems((prev) => prev.filter((existing) => existing.id !== item.id));
      toast({ title: action === "approve" ? "Approved" : "Rejected" });
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : "Decision failed" });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card className="space-y-3 p-4">
      <h2 className="font-display text-lg font-extrabold text-ink">{title}</h2>
      {loading && items.length === 0 ? (
        <div className="space-y-2">
          <Skeleton width="100%" height="96px" />
          <Skeleton width="100%" height="96px" />
        </div>
      ) : null}
      {!loading && items.length === 0 ? <EmptyState icon={emptyIcon} title={emptyTitle} /> : null}
      <ul className="space-y-3">
        {items.map((item) => (
          <li key={item.id}>
            <Card className="space-y-3 p-3">
              <p className="text-sm text-ink">{line(item)}</p>
              <EvidenceStrip base={evidenceBase(item)} count={evidenceCount(item)} />
              <DecideActions
                busy={busyId === item.id}
                onApprove={(note) => void decide(item, "approve", note)}
                onReject={(note) => void decide(item, "reject", note)}
              />
            </Card>
          </li>
        ))}
      </ul>
      {nextCursor ? <Button onClick={() => void load(nextCursor)}>Load more</Button> : null}
    </Card>
  );
}

export function ClaimsManager() {
  return (
    <main className="mx-auto max-w-3xl space-y-6 p-4">
      <h1 className="text-xl font-bold text-ink">Claims &amp; verification</h1>
      <QueueSection<AdminClaim>
        title="Claim queue"
        emptyIcon="🏪"
        emptyTitle="No pending claims"
        listPath="/directory/claims"
        evidenceBase={(item) => `/api/admin/directory/claims/${item.id}/evidence`}
        evidenceCount={(item) => item.evidence_count}
        decidePath={(item) => `/directory/claims/${item.id}`}
        line={(item) => `${item.business_name} - claimed by ${item.claimant_user_id}`}
      />
      <QueueSection<AdminVerification>
        title="Verification queue"
        emptyIcon="✅"
        emptyTitle="No pending verifications"
        listPath="/directory/verifications"
        evidenceBase={(item) => `/api/admin/directory/verifications/${item.id}/docs`}
        evidenceCount={(item) => item.doc_count}
        decidePath={(item) => `/directory/verifications/${item.id}`}
        line={(item) => `${item.business_name} - ${item.method}`}
      />
    </main>
  );
}
