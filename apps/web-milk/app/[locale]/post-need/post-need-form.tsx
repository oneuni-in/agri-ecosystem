"use client";

import { Button, Card, cn, LOC_COOKIE, parseLocCookie } from "@agri/ui";
import { useAgriUser } from "@agri/auth-client/react";
import { useEffect, useState, type FormEvent } from "react";

import { Link } from "@/i18n/navigation";

import { VoiceRecorder } from "./voice-recorder";

type MilkType = "cow" | "buffalo" | "goat" | "mixed";
type Schedule = "daily" | "alternate_days" | "weekly";
type DeliveryTime = "morning" | "evening" | "any";
type Phase = "form" | "submitting" | "done" | "no_coverage" | "error";

const DRAFT_KEY = "post-need-draft";

const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";

const MILK_TYPES: { value: MilkType; icon: string; label: string; vern: string }[] = [
  { value: "cow", icon: "🐄", label: "Cow", vern: "பசு" },
  { value: "buffalo", icon: "🐃", label: "Buffalo", vern: "எருமை" },
  { value: "goat", icon: "🐐", label: "Goat", vern: "ஆடு" },
  { value: "mixed", icon: "🥛", label: "Mixed", vern: "கலப்பு" },
];

const SCHEDULES: { value: Schedule; icon: string; label: string; vern: string }[] = [
  { value: "daily", icon: "📅", label: "Daily", vern: "தினமும்" },
  { value: "alternate_days", icon: "📆", label: "Alternate days", vern: "மாற்று நாள்" },
  { value: "weekly", icon: "🗓", label: "Weekly", vern: "வாரம்" },
];

const TIMES: { value: DeliveryTime; icon: string; label: string; vern: string }[] = [
  { value: "morning", icon: "🌅", label: "Morning", vern: "காலை" },
  { value: "evening", icon: "🌇", label: "Evening", vern: "மாலை" },
  { value: "any", icon: "🕐", label: "Any time", vern: "எப்போதும்" },
];

interface Draft {
  milkType: MilkType;
  qty: string;
  schedule: Schedule;
  deliveryTime: DeliveryTime;
  pincode: string;
  note: string;
}

function readCookiePincode(): string {
  const raw = document.cookie
    .split("; ")
    .find((part) => part.startsWith(`${LOC_COOKIE}=`))
    ?.slice(LOC_COOKIE.length + 1);
  return parseLocCookie(raw)?.pincode ?? "";
}

function AlertNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

/** Icon-first selectable tile row (design laws 1 + 7: icon + English +
 * mother-tongue on every choice, ≥44px targets, aria-pressed state). */
function TileRow<T extends string>({
  options,
  value,
  onChange,
  testPrefix,
}: {
  options: { value: T; icon: string; label: string; vern: string }[];
  value: T;
  onChange: (next: T) => void;
  testPrefix: string;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          data-testid={`${testPrefix}-${option.value.replaceAll("_", "-")}`}
          onClick={() => onChange(option.value)}
          className={cn(
            "min-h-[56px] min-w-[84px] rounded-card border px-3 py-2 text-center",
            value === option.value
              ? "border-brand bg-brand-soft font-bold text-ink"
              : "border-line bg-card text-ink",
          )}
        >
          <span className="block text-[20px]" aria-hidden>
            {option.icon}
          </span>
          <span className="block text-[12px]">{option.label}</span>
          <span className="vern block text-[11px] text-sub">{option.vern}</span>
        </button>
      ))}
    </div>
  );
}

/**
 * D25 "post my need": guest-friendly via draft-then-OTP — the filled form is
 * saved to sessionStorage, the user completes phone+OTP at web-id (which
 * creates the progressive account, D07/D11), and the draft is restored on
 * return. Inline status only (no ToastProvider on web-milk, LeadForm idiom).
 */
export function PostNeedForm() {
  const { status } = useAgriUser({ autoSilentSso: false });
  const [milkType, setMilkType] = useState<MilkType>("cow");
  const [qty, setQty] = useState("1");
  const [schedule, setSchedule] = useState<Schedule>("daily");
  const [deliveryTime, setDeliveryTime] = useState<DeliveryTime>("any");
  const [pincode, setPincode] = useState("");
  const [note, setNote] = useState("");
  const [voiceBlob, setVoiceBlob] = useState<Blob | null>(null);
  const [phase, setPhase] = useState<Phase>("form");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [routedCount, setRoutedCount] = useState(0);
  const [voiceFailed, setVoiceFailed] = useState(false);
  const [interestSent, setInterestSent] = useState(false);

  useEffect(() => {
    // draft (set before an OTP login round-trip) wins over the location cookie
    try {
      const raw = sessionStorage.getItem(DRAFT_KEY);
      if (raw) {
        const draft = JSON.parse(raw) as Draft;
        setMilkType(draft.milkType);
        setQty(draft.qty);
        setSchedule(draft.schedule);
        setDeliveryTime(draft.deliveryTime);
        setNote(draft.note);
        setPincode(draft.pincode || readCookiePincode());
        return;
      }
    } catch {
      // fall through to cookie prefill
    }
    setPincode(readCookiePincode());
  }, []);

  const saveDraft = () => {
    const draft: Draft = { milkType, qty, schedule, deliveryTime, pincode, note };
    try {
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch {
      // storage full/blocked: the redirect still works, the draft is lost
    }
  };

  const stepQty = (delta: number) => {
    const next = Math.min(100, Math.max(0.5, (Number.parseFloat(qty) || 1) + delta));
    setQty(String(next));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (status !== "authenticated") {
      saveDraft();
      window.location.href = `/api/auth/login?next=${encodeURIComponent("/post-need")}`;
      return;
    }
    setPhase("submitting");
    setErrorText(null);
    try {
      const res = await fetch("/api/leads/needs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          pincode,
          payload: {
            qty_liters: qty,
            milk_type: milkType,
            schedule,
            delivery_time: deliveryTime,
            ...(note.trim() ? { note: note.trim() } : {}),
          },
        }),
      });
      if (res.status === 201) {
        const body = (await res.json()) as { id: string; routed_count: number };
        setRoutedCount(body.routed_count);
        if (voiceBlob) {
          const form = new FormData();
          form.append("file", voiceBlob, "note");
          const voiceRes = await fetch(`/api/leads/needs/${body.id}/voice`, {
            method: "POST",
            body: form,
          });
          // best-effort: a voice failure must not undo the posted need
          setVoiceFailed(voiceRes.status !== 201);
        }
        sessionStorage.removeItem(DRAFT_KEY);
        setPhase("done");
        return;
      }
      const body = (await res.json().catch(() => null)) as { detail?: string } | null;
      if (body?.detail === "no_coverage") {
        setPhase("no_coverage");
        return;
      }
      if (res.status === 429) {
        setErrorText("Daily limit reached — please try again tomorrow.");
      } else if (body?.detail === "invalid_payload") {
        setErrorText("Please check the details you entered.");
      } else {
        setErrorText("Could not post — please try again.");
      }
      setPhase("form");
    } catch {
      setErrorText("Could not post — please try again.");
      setPhase("form");
    }
  };

  const sendInterest = async () => {
    try {
      await fetch("/api/leads/pincode-interest", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ pincode, milk_type: milkType }),
      });
    } catch {
      // capture is best-effort by design (NotifyMe precedent)
    }
    setInterestSent(true);
  };

  if (phase === "done") {
    return (
      <Card className="space-y-2 p-4" data-testid="need-posted">
        <h2 className="font-display text-[18px] font-extrabold text-ink">
          🎉 Sent to {routedCount} vendor{routedCount === 1 ? "" : "s"} near you
        </h2>
        <p className="vern text-[13px] text-sub">
          {routedCount} விற்பனையாளர்களுக்கு அனுப்பப்பட்டது
        </p>
        {voiceFailed ? (
          <p className="text-[13px] text-sub">
            (Your voice note could not be attached — the need itself was sent.)
          </p>
        ) : null}
        <p className="text-[13px] text-sub">They will reply here — track everything in one place.</p>
        <Link
          href="/my-needs"
          className="inline-block min-h-[44px] rounded-btn bg-brand px-4 py-3 text-[13px] font-bold text-white no-underline"
        >
          See my needs · என் தேவைகள்
        </Link>
      </Card>
    );
  }

  if (phase === "no_coverage") {
    return (
      <Card className="space-y-2 p-4" data-testid="need-no-coverage">
        <h2 className="font-display text-[16px] font-extrabold text-ink">
          No vendors here yet — we&apos;ll tell them you&apos;re waiting
        </h2>
        <p className="text-[13px] text-sub">
          No milk vendor covers {pincode} on Milk.in yet. We record the demand and prioritise
          onboarding vendors where people are waiting.
        </p>
        {interestSent ? (
          <p className="text-[13px] font-semibold text-ink" data-testid="notify-done">
            🎉 Noted — we&apos;ll be in touch as vendors join.
          </p>
        ) : (
          <Button
            type="button"
            variant="brand"
            className="max-w-[240px]"
            onClick={() => void sendInterest()}
          >
            Tell me when vendors join
          </Button>
        )}
        <Button
          type="button"
          variant="ghost"
          className="max-w-[200px]"
          onClick={() => setPhase("form")}
        >
          ← Change pincode
        </Button>
      </Card>
    );
  }

  const submitting = phase === "submitting";
  const authed = status === "authenticated";

  return (
    <Card className="p-4">
      <form
        className="space-y-4"
        data-testid="post-need-form"
        onSubmit={(event) => void submit(event)}
      >
        <fieldset className="space-y-2">
          <legend className="text-[13px] font-semibold text-ink">
            Milk type <span className="vern font-normal">· பால் வகை</span>
          </legend>
          <TileRow
            options={MILK_TYPES}
            value={milkType}
            onChange={setMilkType}
            testPrefix="milk-type"
          />
        </fieldset>

        <div className="space-y-1">
          <label htmlFor="need-qty" className="block text-[13px] font-semibold text-ink">
            Litres per delivery <span className="vern font-normal">· லிட்டர்</span>
          </label>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              className="max-w-[56px] text-[18px]"
              aria-label="Less milk"
              onClick={() => stepQty(-0.5)}
            >
              −
            </Button>
            <input
              id="need-qty"
              required
              type="number"
              inputMode="decimal"
              min="0.5"
              max="100"
              step="0.5"
              value={qty}
              onChange={(event) => setQty(event.target.value)}
              className={cn(FIELD, "mt-0 max-w-[110px] text-center text-[16px] font-bold")}
              data-testid="qty-input"
            />
            <Button
              type="button"
              variant="ghost"
              className="max-w-[56px] text-[18px]"
              aria-label="More milk"
              onClick={() => stepQty(0.5)}
            >
              +
            </Button>
          </div>
        </div>

        <fieldset className="space-y-2">
          <legend className="text-[13px] font-semibold text-ink">
            How often <span className="vern font-normal">· எத்தனை முறை</span>
          </legend>
          <TileRow
            options={SCHEDULES}
            value={schedule}
            onChange={setSchedule}
            testPrefix="schedule"
          />
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="text-[13px] font-semibold text-ink">
            Delivery time <span className="vern font-normal">· நேரம்</span>
          </legend>
          <TileRow options={TIMES} value={deliveryTime} onChange={setDeliveryTime} testPrefix="time" />
        </fieldset>

        <label className="block text-[13px] font-semibold text-ink">
          Pincode <span className="vern font-normal">· அஞ்சல் குறியீடு</span>
          <input
            required
            inputMode="numeric"
            pattern="\d{6}"
            maxLength={6}
            value={pincode}
            onChange={(event) => setPincode(event.target.value)}
            className={FIELD}
            data-testid="need-pincode"
          />
        </label>

        <label className="block text-[13px] font-semibold text-ink">
          Anything else? <span className="font-normal text-sub">(optional)</span>
          <textarea
            maxLength={500}
            rows={2}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            className={cn(FIELD, "min-h-[64px]")}
          />
        </label>

        <VoiceRecorder onBlob={setVoiceBlob} />

        {errorText ? <AlertNotice>{errorText}</AlertNotice> : null}

        {status === "loading" ? (
          <Button type="button" variant="ghost" className="max-w-[260px]" disabled>
            Loading...
          </Button>
        ) : (
          <Button
            type="submit"
            variant="brand"
            disabled={submitting}
            className="max-w-[300px]"
            data-testid={authed ? "post-need-submit" : "post-need-login"}
          >
            {submitting
              ? "Sending..."
              : authed
                ? "Post my need · அனுப்பு"
                : "📱 Continue with phone · OTP"}
          </Button>
        )}
        {!authed && status !== "loading" ? (
          <p className="text-[12px] text-sub">
            Your details stay filled in — verify your phone with a one-time code and we post it.
          </p>
        ) : null}
      </form>
    </Card>
  );
}
