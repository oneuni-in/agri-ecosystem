"use client";

import { Button, Card, cn, LOC_COOKIE, parseLocCookie, TypeFilter } from "@agri/ui";
import { useAgriUser } from "@agri/auth-client/react";
import { useLocale, useTranslations } from "next-intl";
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

/** The D25 need enums, with their icons and the reference's designed Tamil
 * accents (shown on /en only — ta/hi labels come fully translated from the
 * ui.needs catalog). The value sets are the FORM's own fixed enums, so their
 * labels are i18n content (allowed), not taxonomy. */
const MILK_TYPES: { value: MilkType; icon: string; vern: string }[] = [
  { value: "cow", icon: "🐄", vern: "பசு" },
  { value: "buffalo", icon: "🐃", vern: "எருமை" },
  { value: "goat", icon: "🐐", vern: "ஆடு" },
  { value: "mixed", icon: "🥛", vern: "கலப்பு" },
];

const SCHEDULES: { value: Schedule; key: string; icon: string; vern: string }[] = [
  { value: "daily", key: "daily", icon: "📅", vern: "தினமும்" },
  { value: "alternate_days", key: "alternateDays", icon: "📆", vern: "மாற்று நாள்" },
  { value: "weekly", key: "weekly", icon: "🗓", vern: "வாரம்" },
];

const TIMES: { value: DeliveryTime; icon: string; vern: string }[] = [
  { value: "morning", icon: "🌅", vern: "காலை" },
  { value: "evening", icon: "🌇", vern: "மாலை" },
  { value: "any", icon: "🕐", vern: "எப்போதும்" },
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

/**
 * D25 "post my need": guest-friendly via draft-then-OTP — the filled form is
 * saved to sessionStorage, the user completes phone+OTP at web-id (which
 * creates the progressive account, D07/D11), and the draft is restored on
 * return. Inline status only (no ToastProvider on web-milk, LeadForm idiom).
 *
 * U1b: the selectable tile rows render the catalog `TypeFilter` composite
 * (the §5c chip — icon + label + vernacular + aria-pressed), and every label
 * reads from the ui.needs catalog.
 */
export function PostNeedForm() {
  const { status } = useAgriUser({ autoSilentSso: false });
  const t = useTranslations("ui.needs");
  const locale = useLocale();
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

  // The reference's designed Tamil accents render on /en only.
  const vern = (text: string): string | undefined => (locale === "en" ? text : undefined);

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
        setErrorText(t("errorLimit"));
      } else if (body?.detail === "invalid_payload") {
        setErrorText(t("errorInvalid"));
      } else {
        setErrorText(t("errorGeneric"));
      }
      setPhase("form");
    } catch {
      setErrorText(t("errorGeneric"));
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
          {t("doneTitle", { count: routedCount })}
        </h2>
        {locale === "en" ? (
          <p className="vern text-[13px] text-sub">
            {routedCount} விற்பனையாளர்களுக்கு அனுப்பப்பட்டது
          </p>
        ) : null}
        {voiceFailed ? <p className="text-[13px] text-sub">{t("doneVoiceFailed")}</p> : null}
        <p className="text-[13px] text-sub">{t("doneTrack")}</p>
        <Link
          href="/my-needs"
          className="inline-block min-h-[44px] rounded-btn bg-brand px-4 py-3 text-[13px] font-bold text-white no-underline"
        >
          {t("seeMyNeeds")}
          {locale === "en" ? <span className="vern font-normal"> · என் தேவைகள்</span> : null}
        </Link>
      </Card>
    );
  }

  if (phase === "no_coverage") {
    return (
      <Card className="space-y-2 p-4" data-testid="need-no-coverage">
        <h2 className="font-display text-[16px] font-extrabold text-ink">
          {t("noCoverageTitle")}
        </h2>
        <p className="text-[13px] text-sub">{t("noCoverageBody", { pincode })}</p>
        {interestSent ? (
          <p className="text-[13px] font-semibold text-ink" data-testid="notify-done">
            {t("noCoverageNoted")}
          </p>
        ) : (
          <Button
            type="button"
            variant="brand"
            className="max-w-[240px]"
            onClick={() => void sendInterest()}
          >
            {t("noCoverageNotify")}
          </Button>
        )}
        <Button
          type="button"
          variant="ghost"
          className="max-w-[200px]"
          onClick={() => setPhase("form")}
        >
          {t("changePincode")}
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
            {t("milkTypeLegend")}
            {locale === "en" ? <span className="vern font-normal"> · பால் வகை</span> : null}
          </legend>
          <div className="flex flex-wrap gap-2">
            {MILK_TYPES.map((option) => (
              <TypeFilter
                key={option.value}
                icon={option.icon}
                label={t(`types.${option.value}`)}
                vernacular={vern(option.vern)}
                active={milkType === option.value}
                data-testid={`milk-type-${option.value}`}
                onClick={() => setMilkType(option.value)}
              />
            ))}
          </div>
        </fieldset>

        <div className="space-y-1">
          <label htmlFor="need-qty" className="block text-[13px] font-semibold text-ink">
            {t("qtyLabel")}
            {locale === "en" ? <span className="vern font-normal"> · லிட்டர்</span> : null}
          </label>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              className="max-w-[56px] text-[18px]"
              aria-label={t("less")}
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
              aria-label={t("more")}
              onClick={() => stepQty(0.5)}
            >
              +
            </Button>
          </div>
        </div>

        <fieldset className="space-y-2">
          <legend className="text-[13px] font-semibold text-ink">
            {t("scheduleLegend")}
            {locale === "en" ? <span className="vern font-normal"> · எத்தனை முறை</span> : null}
          </legend>
          <div className="flex flex-wrap gap-2">
            {SCHEDULES.map((option) => (
              <TypeFilter
                key={option.value}
                icon={option.icon}
                label={t(`schedules.${option.key}`)}
                vernacular={vern(option.vern)}
                active={schedule === option.value}
                data-testid={`schedule-${option.value.replaceAll("_", "-")}`}
                onClick={() => setSchedule(option.value)}
              />
            ))}
          </div>
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="text-[13px] font-semibold text-ink">
            {t("timeLegend")}
            {locale === "en" ? <span className="vern font-normal"> · நேரம்</span> : null}
          </legend>
          <div className="flex flex-wrap gap-2">
            {TIMES.map((option) => (
              <TypeFilter
                key={option.value}
                icon={option.icon}
                label={t(`times.${option.value}`)}
                vernacular={vern(option.vern)}
                active={deliveryTime === option.value}
                data-testid={`time-${option.value}`}
                onClick={() => setDeliveryTime(option.value)}
              />
            ))}
          </div>
        </fieldset>

        <label className="block text-[13px] font-semibold text-ink">
          {t("pincodeLabel")}
          {locale === "en" ? <span className="vern font-normal"> · அஞ்சல் குறியீடு</span> : null}
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
          {t("noteLabel")} <span className="font-normal text-sub">{t("optional")}</span>
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
            {t("loading")}
          </Button>
        ) : (
          <Button
            type="submit"
            variant="brand"
            disabled={submitting}
            className="max-w-[300px]"
            data-testid={authed ? "post-need-submit" : "post-need-login"}
          >
            {submitting ? (
              t("sending")
            ) : authed ? (
              <>
                {t("submit")}
                {locale === "en" ? <span className="vern"> · அனுப்பு</span> : null}
              </>
            ) : (
              t("continueOtp")
            )}
          </Button>
        )}
        {!authed && status !== "loading" ? (
          <p className="text-[12px] text-sub">{t("draftKept")}</p>
        ) : null}
      </form>
    </Card>
  );
}
