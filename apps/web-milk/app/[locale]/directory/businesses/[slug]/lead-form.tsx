"use client";

import { Button, Card, cn } from "@agri/ui";
import { useState, type FormEvent } from "react";

type Kind = "contact" | "milk_subscription";
type SubmitState = "idle" | "submitting" | "done";

// Copied verbatim from claim-form.tsx's input styling (D16 idiom) so the two
// forms on this page read as one system.
const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";
const LABEL = "block text-[13px] font-semibold text-ink";

const ERROR_MESSAGES: Record<string, string> = {
  business_not_covered: "This business does not currently serve your pincode.",
  no_coverage: "No business here covers that pincode yet.",
  invalid_payload: "Please check the details you entered.",
};

function AlertNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

/**
 * "Form is the fallback" (design law): rendered below RevealContact. Guests
 * can submit (via /api/leads, which attaches a bearer only when a session
 * exists) - no ToastProvider on web-agri, so status is inline state, same
 * pattern as ClaimForm.
 */
export function LeadForm({
  businessId,
  defaultPincode,
  milkVertical,
}: {
  businessId: string;
  defaultPincode: string;
  milkVertical: boolean;
}) {
  const [kind, setKind] = useState<Kind>("contact");
  const [state, setState] = useState<SubmitState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [pincode, setPincode] = useState(defaultPincode);
  const [message, setMessage] = useState("");
  const [qtyLiters, setQtyLiters] = useState("1");
  const [milkType, setMilkType] = useState("cow");
  const [schedule, setSchedule] = useState("daily");

  const submitting = state === "submitting";

  if (state === "done") {
    return (
      <Card className="space-y-2 p-4">
        <h2 className="font-display text-[16px] font-extrabold text-ink">Enquiry sent</h2>
        <p className="text-[13px] text-sub">The business will get back to you shortly.</p>
      </Card>
    );
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setState("submitting");
    setError(null);
    const payload =
      kind === "contact" ? { message } : { qty_liters: qtyLiters, milk_type: milkType, schedule };
    try {
      const res = await fetch("/api/leads/inquiries", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ type: kind, business_id: businessId, pincode, payload }),
      });
      if (res.status === 201) {
        setState("done");
        return;
      }
      const body = (await res.json().catch(() => null)) as { detail?: string } | null;
      setError(
        (body?.detail && ERROR_MESSAGES[body.detail]) ??
          "Could not send — please check your details and try again.",
      );
      setState("idle");
    } catch {
      setError("Could not send — please try again.");
      setState("idle");
    }
  };

  return (
    <Card className="space-y-3 p-4">
      <header className="space-y-1">
        <h2 className="font-display text-[16px] font-extrabold text-ink">Send an enquiry</h2>
        <p className="text-[13px] text-sub">
          Prefer to talk? Use call or WhatsApp above — this form is the fallback.
        </p>
      </header>
      <form className="space-y-3" onSubmit={(event) => void submit(event)}>
        {milkVertical ? (
          <div className="flex gap-2">
            <Button
              type="button"
              variant={kind === "contact" ? "brand" : "ghost"}
              className="max-w-[200px]"
              onClick={() => setKind("contact")}
            >
              Message
            </Button>
            <Button
              type="button"
              variant={kind === "milk_subscription" ? "brand" : "ghost"}
              className="max-w-[200px]"
              onClick={() => setKind("milk_subscription")}
            >
              Milk subscription
            </Button>
          </div>
        ) : null}
        <label className={LABEL}>
          Pincode
          <input
            required
            inputMode="numeric"
            pattern="\d{6}"
            maxLength={6}
            value={pincode}
            onChange={(event) => setPincode(event.target.value)}
            className={FIELD}
          />
        </label>
        {kind === "contact" ? (
          <label className={LABEL}>
            Message
            <textarea
              required
              maxLength={2000}
              rows={3}
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              className={cn(FIELD, "min-h-[88px]")}
            />
          </label>
        ) : (
          <div className="space-y-3">
            <label className={LABEL}>
              Litres per day
              <input
                required
                type="number"
                min="0.5"
                max="100"
                step="0.5"
                value={qtyLiters}
                onChange={(event) => setQtyLiters(event.target.value)}
                className={FIELD}
              />
            </label>
            <label className={LABEL}>
              Milk type
              <select
                value={milkType}
                onChange={(event) => setMilkType(event.target.value)}
                className={FIELD}
              >
                <option value="cow">Cow</option>
                <option value="buffalo">Buffalo</option>
                <option value="goat">Goat</option>
                <option value="mixed">Mixed</option>
              </select>
            </label>
            <label className={LABEL}>
              Schedule
              <select
                value={schedule}
                onChange={(event) => setSchedule(event.target.value)}
                className={FIELD}
              >
                <option value="daily">Daily</option>
                <option value="alternate_days">Alternate days</option>
                <option value="weekly">Weekly</option>
              </select>
            </label>
          </div>
        )}
        {error ? <AlertNotice>{error}</AlertNotice> : null}
        <Button type="submit" variant="brand" disabled={submitting} className="max-w-[240px]">
          {submitting ? "Sending..." : "Send enquiry"}
        </Button>
      </form>
    </Card>
  );
}
