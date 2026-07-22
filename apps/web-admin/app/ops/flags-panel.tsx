"use client";

/**
 * D21 Task 14: platform flag kill switches (Task 11's /admin/ops/flags).
 * Both GET and PUT are super_admin-only in admin_router.py, so a staff
 * session's GET 403s - rather than crash, this shows a restricted notice in
 * place of the switch list. Each toggle opens a confirm Modal (a flip is a
 * business-level act - D20 PRE-FLAG-FLIP checklist), applies optimistically,
 * and reverts on failure - a 403 (role lost mid-session, or a staff-visible
 * build of this panel one day) surfaces as a toast and the switch snaps back.
 */

import { Button, Card, EmptyState, Modal, Skeleton, cn, useToast } from "@agri/ui";
import { useEffect, useState } from "react";

import { ApiError, getJson, putJson } from "@/lib/api";

interface Flag {
  key: string;
  enabled: boolean;
  description: string;
  updated_at: string;
}

function FlagToggleGlyph({ enabled, busy }: { enabled: boolean; busy: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "relative inline-flex h-[26px] w-[46px] shrink-0 rounded-pill border border-line transition-colors",
        enabled ? "bg-brand" : "bg-ghost",
        busy && "opacity-60",
      )}
    >
      <span
        className={cn(
          "absolute top-[2px] h-[20px] w-[20px] rounded-full bg-card shadow-search transition-transform",
          enabled ? "translate-x-[22px]" : "translate-x-[2px]",
        )}
      />
    </span>
  );
}

export function FlagsPanel() {
  const { toast } = useToast();
  const [flags, setFlags] = useState<Flag[]>([]);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const body = await getJson("/ops/flags");
      setFlags((body.items ?? []) as Flag[]);
      setForbidden(false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setForbidden(true);
      } else {
        toast({ title: error instanceof ApiError ? error.detail : "Could not load flags" });
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const toggle = async (flag: Flag) => {
    const next = !flag.enabled;
    setBusyKey(flag.key);
    setFlags((prev) => prev.map((f) => (f.key === flag.key ? { ...f, enabled: next } : f)));
    try {
      const updated = (await putJson(`/ops/flags/${encodeURIComponent(flag.key)}`, {
        enabled: next,
      })) as unknown as Flag;
      setFlags((prev) => prev.map((f) => (f.key === flag.key ? updated : f)));
      toast({ title: `${flag.key} is now ${next ? "on" : "off"}` });
    } catch (error) {
      setFlags((prev) => prev.map((f) => (f.key === flag.key ? { ...f, enabled: flag.enabled } : f)));
      if (error instanceof ApiError && error.status === 403) {
        toast({ title: "You don't have permission to change flags" });
      } else {
        toast({ title: error instanceof ApiError ? error.detail : "Could not change this flag" });
      }
    } finally {
      setBusyKey(null);
    }
  };

  if (!loading && forbidden) {
    return (
      <Card className="space-y-3 p-4">
        <h2 className="font-display text-lg font-extrabold text-ink">Flags</h2>
        <EmptyState
          icon="🔒"
          title="Flags are restricted"
          description="Only super_admin can view or change platform flags."
        />
      </Card>
    );
  }

  const hasCoinsFlag = flags.some((flag) => flag.key.includes("coins"));

  return (
    <Card className="space-y-3 p-4">
      <h2 className="font-display text-lg font-extrabold text-ink">Flags</h2>
      {hasCoinsFlag ? (
        <p className="text-[13px] text-sub">
          For coins reward-rule switches, use the{" "}
          <a href="/coins" className="text-brand underline">
            Coins
          </a>{" "}
          console instead.
        </p>
      ) : null}
      {loading ? (
        <div className="space-y-2">
          <Skeleton width="100%" height="56px" />
          <Skeleton width="100%" height="56px" />
        </div>
      ) : null}
      {!loading && flags.length === 0 ? <EmptyState icon="🚩" title="No flags configured" /> : null}
      <ul className="space-y-2">
        {flags.map((flag) => (
          <li key={flag.key}>
            <Card className="flex items-center justify-between gap-3 p-3">
              <div className="space-y-0.5">
                <p className="text-sm font-semibold text-ink">{flag.key}</p>
                <p className="text-xs text-sub">{flag.description}</p>
              </div>
              <Modal
                trigger={
                  <button
                    type="button"
                    aria-label={`Toggle ${flag.key}`}
                    disabled={busyKey === flag.key}
                  >
                    <FlagToggleGlyph enabled={flag.enabled} busy={busyKey === flag.key} />
                  </button>
                }
                title="Kill switch"
                description={`This flips \`${flag.key}\` platform-wide.`}
                closeLabel="Cancel"
              >
                <Button variant="brand" disabled={busyKey === flag.key} onClick={() => void toggle(flag)}>
                  Confirm {flag.enabled ? "turn off" : "turn on"}
                </Button>
              </Modal>
            </Card>
          </li>
        ))}
      </ul>
    </Card>
  );
}
