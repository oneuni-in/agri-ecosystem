"use client";

import {
  ConsoleLabel,
  ConsoleNotice,
  ConsolePolicyNote,
  consoleControlClass,
  consolePrimaryButtonClass,
} from "@agri/ui";
import Link from "next/link";
import { useEffect, useState } from "react";

import { GSTIN_PATTERN, readGstin, writeGstin } from "@/lib/advertiser";

/**
 * A-U7 W4 — the one field on the A3 registration page that can actually be
 * saved.
 *
 * The reference asks for legal/trade name, business type, GSTIN, PAN, a
 * billing contact and a billing email. Name and contact already exist — the
 * business record and the AgriID-verified phone — and are shown as facts
 * rather than as editable inputs that would write nowhere. Business type,
 * PAN and billing email have no column anywhere, so they are ABSENT: a form
 * field that silently discards what someone typed is worse than no field.
 *
 * GSTIN is remembered per-browser and prefilled into the wizard's pay step,
 * where it becomes `buyer_gstin` on the order and lands on the tax invoice.
 */
export function BillingForm({
  businessName,
  agriId,
}: {
  businessName: string | null;
  /** The account the invoice is billed to. The session carries no phone —
   * the AgriID is the identity that was OTP-verified. */
  agriId: string;
}) {
  const [gstin, setGstin] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Read on mount, not during render: localStorage does not exist on the
  // server and reading it in render would break hydration.
  useEffect(() => {
    setGstin(readGstin());
  }, []);

  const save = () => {
    const value = gstin.trim().toUpperCase();
    if (value !== "" && !GSTIN_PATTERN.test(value)) {
      setError("GSTIN must be exactly 15 characters — digits and uppercase letters.");
      setSaved(false);
      return;
    }
    writeGstin(value);
    setGstin(value);
    setError(null);
    setSaved(true);
  };

  return (
    <div className="space-y-3">
      {/* Facts, not inputs: these come from the listing and from AgriID, and
          there is nothing here for this page to write. */}
      <dl className="m-0">
        <div className="flex justify-between gap-3 border-b border-cream-line py-2 text-xs">
          <dt className="text-muted">Trade name</dt>
          <dd className="text-right font-medium text-ink">{businessName ?? "—"}</dd>
        </div>
        <div className="flex justify-between gap-3 py-2 text-xs">
          <dt className="text-muted">Billing account</dt>
          <dd className="text-right font-medium text-ink">{agriId} · verified ✓</dd>
        </div>
      </dl>

      <label className="block">
        <ConsoleLabel>
          GSTIN{" "}
          <span className="font-normal text-muted">(optional — needed for a GST invoice)</span>
        </ConsoleLabel>
        <input
          className={consoleControlClass}
          value={gstin}
          maxLength={15}
          autoComplete="off"
          spellCheck={false}
          placeholder="33ABCDE1234F1Z5"
          onChange={(e) => {
            setGstin(e.target.value.toUpperCase());
            setError(null);
            setSaved(false);
          }}
        />
      </label>

      {error ? <ConsoleNotice tone="alert">{error}</ConsoleNotice> : null}
      {saved ? (
        <ConsoleNotice tone="ok">
          Saved on this device — it will be filled in when you pay for a campaign.
        </ConsoleNotice>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={consolePrimaryButtonClass} onClick={save}>
          Save GSTIN
        </button>
        <Link href="/business/ads" className={consolePrimaryButtonClass} prefetch={false}>
          Create your first campaign →
        </Link>
      </div>

      <ConsolePolicyNote>
        Saved on this device only, so the wizard can fill it in for you — it is not an account
        record, and it is not consent to anything. Business type, PAN and a separate billing email
        are on the reference design but have nowhere to be stored yet, so this page does not ask
        for them.
      </ConsolePolicyNote>
    </div>
  );
}
