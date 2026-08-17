"use client";

/**
 * A-U1 W2 — the Soon landing's notify-me island. POSTs to the guest-capable
 * BFF proxy `/api/leads/pincode-interest` → backend `/leads/pincode-interest`
 * (the D23 pincode-interest module, directory/leads_router.py). Schema
 * `PincodeInterestCreateIn`: `pincode` required (^\d{6}$), `contact`
 * optional (≤120), `milk_type` optional (milk.in's field — omitted here).
 * A signed-in visitor is attributed server-side by the proxy's bearer;
 * the optional contact field is for everyone else.
 */
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

type Status = "idle" | "sending" | "done" | "error";

export function NotifyMeForm() {
  const t = useTranslations("ui.agriHome.soonPage");
  const [pincode, setPincode] = useState("");
  const [contact, setContact] = useState("");
  const [status, setStatus] = useState<Status>("idle");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (status === "sending") return;
    setStatus("sending");
    try {
      const res = await fetch("/api/leads/pincode-interest", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          pincode: pincode.trim(),
          contact: contact.trim() || null,
        }),
      });
      setStatus(res.status === 201 ? "done" : "error");
    } catch {
      setStatus("error");
    }
  }

  if (status === "done") {
    return (
      <p
        data-testid="notify-me-done"
        className="mt-4 max-w-[520px] rounded-card border border-accent bg-trust-bg px-4 py-3.5 text-[13px] text-ink"
      >
        {t("done", { pincode: pincode.trim() })}
      </p>
    );
  }

  return (
    <form
      data-testid="notify-me-form"
      onSubmit={submit}
      className="mt-4 flex max-w-[520px] flex-col gap-2.5 rounded-card border border-cream-line bg-card p-4"
    >
      <b className="text-[13px] font-semibold text-ink">{t("formTitle")}</b>
      <label htmlFor="notify-pincode" className="block">
        <span className="mb-1 block text-[11px] font-medium text-sub">{t("pincodeLabel")}</span>
        <input
          id="notify-pincode"
          type="text"
          inputMode="numeric"
          pattern="\d{6}"
          maxLength={6}
          required
          value={pincode}
          onChange={(e) => setPincode(e.target.value)}
          placeholder={t("pincodePlaceholder")}
          className="min-h-[44px] w-full rounded-btn border border-cream-line bg-card px-3 text-sm text-ink focus:border-brand focus:outline-none"
        />
      </label>
      <label htmlFor="notify-contact" className="block">
        <span className="mb-1 block text-[11px] font-medium text-sub">{t("contactLabel")}</span>
        <input
          id="notify-contact"
          type="text"
          maxLength={120}
          value={contact}
          onChange={(e) => setContact(e.target.value)}
          placeholder={t("contactPlaceholder")}
          className="min-h-[44px] w-full rounded-btn border border-cream-line bg-card px-3 text-sm text-ink focus:border-brand focus:outline-none"
        />
      </label>
      <button
        type="submit"
        disabled={status === "sending"}
        className="inline-flex min-h-[44px] items-center justify-center rounded-btn bg-brand px-5 text-sm font-bold text-white disabled:opacity-60"
      >
        🔔 {t("cta")}
      </button>
      {status === "error" ? (
        <p data-testid="notify-me-error" className="text-[11.5px] text-down">
          {t("error")}
        </p>
      ) : null}
    </form>
  );
}
