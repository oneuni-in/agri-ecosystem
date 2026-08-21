"use client";

/**
 * The DPDP rights block on /account (ID-U1 W4).
 *
 * Identity-wide rights live HERE, on the identity app — the vertical
 * dashboards link into this block rather than each growing their own.
 *
 * It renders only because W4's endpoints exist. The build prompt forbids
 * dead buttons on this page and it is the right rule: a "Delete my AgriID"
 * that does nothing is worse than no button, because the person walks away
 * believing they asked.
 */

import { Button, Card, Modal, useToast } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { ApiError, deleteJson, getJson, postJson } from "../../lib/api";

interface Reveal {
  revealed_at: string;
  business_name: string | null;
  source: string;
}

interface ErasureState {
  status: "none" | "pending" | "held" | "executed" | "cancelled";
  execute_after: string | null;
  requested_at: string | null;
}

export function DpdpBlock({ graceDays }: { graceDays: number }) {
  const t = useTranslations("ui.auth.profile");
  const { toast } = useToast();
  const [erasure, setErasure] = useState<ErasureState | null>(null);
  const [reveals, setReveals] = useState<Reveal[] | null>(null);
  const [busy, setBusy] = useState(false);

  const loadErasure = useCallback(async () => {
    try {
      setErasure((await getJson("/identity/dpdp/erasure")) as unknown as ErasureState);
    } catch {
      setErasure({ status: "none", execute_after: null, requested_at: null });
    }
  }, []);

  useEffect(() => {
    void loadErasure();
  }, [loadErasure]);

  const requestDeletion = async () => {
    setBusy(true);
    try {
      setErasure((await postJson("/identity/dpdp/erasure", {})) as unknown as ErasureState);
    } catch (error) {
      toast({ title: error instanceof ApiError ? t("error") : t("error") });
    } finally {
      setBusy(false);
    }
  };

  const withdraw = async () => {
    setBusy(true);
    try {
      await deleteJson("/identity/dpdp/erasure");
      toast({ title: t("dpdpWithdrawn") });
      await loadErasure();
    } catch {
      toast({ title: t("error") });
    } finally {
      setBusy(false);
    }
  };

  const openReveals = async () => {
    setBusy(true);
    try {
      const body = await getJson("/identity/dpdp/reveals");
      setReveals((body.items as Reveal[]) ?? []);
    } catch {
      toast({ title: t("error") });
    } finally {
      setBusy(false);
    }
  };

  const open = erasure?.status === "pending" || erasure?.status === "held";
  const formatDate = (iso: string) =>
    new Intl.DateTimeFormat("en", { day: "numeric", month: "long", year: "numeric" }).format(
      new Date(iso),
    );

  return (
    <Card className="space-y-3 p-4">
      <p className="text-sm font-semibold text-ink">{t("dpdpTitle")}</p>
      <p className="text-sm text-sub">{t("dpdpIntro")}</p>

      <div className="flex flex-wrap gap-2">
        {/* A plain link, not a fetch: the response carries its own
            content-disposition, so the browser saves the file without this
            page having to hold a whole personal archive in memory first. */}
        <a
          href="/api/id/identity/dpdp/export"
          className="tap-target inline-flex min-h-[44px] items-center rounded-btn border border-line bg-card px-3 text-sm font-bold text-ink"
        >
          ⬇ {t("dpdpExport")}
        </a>
        <Button variant="ghost" className="flex-none" disabled={busy} onClick={() => void openReveals()}>
          🔍 {t("dpdpReveals")}
        </Button>
      </div>
      <p className="text-xs text-muted">{t("dpdpExportHint")}</p>

      {reveals !== null && (
        <div className="space-y-2 rounded-btn border border-line bg-cream p-3">
          <p className="text-sm font-semibold text-ink">{t("dpdpReveals")}</p>
          <p className="text-xs text-muted">{t("dpdpRevealsHint")}</p>
          {reveals.length === 0 ? (
            <p className="text-sm text-sub">{t("dpdpRevealsEmpty")}</p>
          ) : (
            <ul className="space-y-1">
              {reveals.map((r) => (
                <li key={`${r.revealed_at}-${r.business_name}`} className="text-sm text-sub">
                  {r.business_name ?? "—"} · {formatDate(r.revealed_at)}
                </li>
              ))}
            </ul>
          )}
          <Button variant="ghost" onClick={() => setReveals(null)}>
            {t("dpdpRevealsClose")}
          </Button>
        </div>
      )}

      {/* The deletion half renders the state the account is actually in. A
          pending request is the important thing on this page while it lasts,
          so it replaces the button rather than sitting beside it. */}
      {open ? (
        <div className="space-y-2 rounded-btn border border-alert-line bg-alert-bg p-3">
          <p className="text-sm text-ink">
            {erasure?.status === "held"
              ? t("dpdpHeld")
              : t("dpdpPending", {
                  date: erasure?.execute_after ? formatDate(erasure.execute_after) : "",
                })}
          </p>
          <Button variant="brand" disabled={busy} onClick={() => void withdraw()}>
            {t("dpdpWithdraw")}
          </Button>
        </div>
      ) : (
        <Modal
          trigger={
            <Button variant="ghost" className="text-down">
              {t("dpdpDelete")}
            </Button>
          }
          title={t("dpdpDeleteConfirmTitle")}
          closeLabel={t("dpdpWithdraw")}
        >
          <div className="flex flex-col gap-3">
            <p className="text-sm text-sub">{t("dpdpDeleteConfirmBody", { days: graceDays })}</p>
            <Button variant="brand" disabled={busy} onClick={() => void requestDeletion()}>
              {t("dpdpDeleteConfirmCta")}
            </Button>
          </div>
        </Modal>
      )}
    </Card>
  );
}
