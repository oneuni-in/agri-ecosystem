"use client";

import { Button, buttonVariants, cn, Modal } from "@agri/ui";
import { useAgriUser } from "@agri/auth-client/react";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

type SubmitState = "idle" | "submitting" | "done" | "exists" | "capped";

// Copied verbatim from review-form.tsx's field styling (D18 idiom) so the
// forms on this page read as one system.
const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";
const LABEL = "block text-[13px] font-semibold text-ink";

const REASONS = ["fake_listing", "wrong_info", "abusive", "fraud_scam", "other"] as const;
type Reason = (typeof REASONS)[number];

function AlertNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

/**
 * M1.5.A report flow. Login-gated (same login-CTA idiom as ReviewForm);
 * POSTs through the auth-forwarding /api/directory BFF proxy. The Modal is
 * uncontrolled (D11 trap: no programmatic close), so success/409/429 states
 * render INSIDE the dialog body. Reports go to the Ops Console only - the
 * copy promises review, never public visibility.
 */
export function ReportDialog({ slug }: { slug: string }) {
  const t = useTranslations("ui.report");
  const { status } = useAgriUser({ autoSilentSso: false });
  const [reason, setReason] = useState<Reason | null>(null);
  const [detail, setDetail] = useState("");
  const [state, setState] = useState<SubmitState>("idle");
  const [error, setError] = useState<string | null>(null);

  if (status === "loading") {
    return null;
  }

  if (status === "unauthenticated") {
    return (
      <a
        href={`/api/auth/login?next=${encodeURIComponent(`/directory/businesses/${slug}`)}`}
        className={cn(buttonVariants({ variant: "ghost" }), "max-w-[280px] no-underline")}
        data-testid="report-login-cta"
      >
        {t("loginCta")}
      </a>
    );
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!reason) {
      setError(t("reasonRequired"));
      return;
    }
    if (reason === "other" && !detail.trim()) {
      setError(t("detailRequired"));
      return;
    }
    setState("submitting");
    setError(null);
    try {
      const res = await fetch(`/api/directory/businesses/${encodeURIComponent(slug)}/report`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          reason,
          ...(detail.trim() ? { detail: detail.trim() } : {}),
        }),
      });
      if (res.status === 201) {
        setState("done");
        return;
      }
      if (res.status === 409) {
        setState("exists");
        return;
      }
      if (res.status === 429) {
        setState("capped");
        return;
      }
      setError(t("error"));
      setState("idle");
    } catch {
      setError(t("error"));
      setState("idle");
    }
  };

  const body =
    state === "done" ? (
      <p className="text-[13px] font-semibold text-ink" data-testid="report-done">
        {t("done")}
      </p>
    ) : state === "exists" ? (
      <p className="text-[13px] font-semibold text-ink">{t("alreadyReported")}</p>
    ) : state === "capped" ? (
      <p className="text-[13px] font-semibold text-ink">{t("capExceeded")}</p>
    ) : (
      <form className="space-y-3" onSubmit={(event) => void submit(event)}>
        <fieldset>
          <legend className={LABEL}>{t("reasonLabel")}</legend>
          <div className="mt-1 space-y-1.5">
            {REASONS.map((value) => (
              <label
                key={value}
                className="flex min-h-[44px] cursor-pointer items-center gap-2.5 rounded-btn border border-line bg-card px-3 text-[13px] font-semibold text-ink"
              >
                <input
                  type="radio"
                  name="report-reason"
                  value={value}
                  checked={reason === value}
                  onChange={() => setReason(value)}
                  className="h-4 w-4 accent-accent"
                />
                {t(`reasons.${value}`)}
              </label>
            ))}
          </div>
        </fieldset>
        <label className={LABEL}>
          {reason === "other" ? t("detailLabelRequired") : t("detailLabel")}
          <textarea
            maxLength={1000}
            rows={3}
            value={detail}
            onChange={(event) => setDetail(event.target.value)}
            className={cn(FIELD, "min-h-[88px]")}
          />
        </label>
        {error ? <AlertNotice>{error}</AlertNotice> : null}
        <Button
          type="submit"
          variant="brand"
          disabled={state === "submitting"}
          className="max-w-[240px]"
        >
          {state === "submitting" ? t("submitting") : t("submit")}
        </Button>
      </form>
    );

  return (
    <Modal
      trigger={
        <Button variant="ghost" className="max-w-[280px]" data-testid="report-trigger">
          {t("trigger")}
        </Button>
      }
      title={t("title")}
      description={t("description")}
    >
      {body}
    </Modal>
  );
}
