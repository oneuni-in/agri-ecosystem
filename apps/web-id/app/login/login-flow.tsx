"use client";

import { Button, Card, CategoryTile, OtpInput } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { use, useEffect, useRef, useState } from "react";

import { ApiError, getJson, postJson } from "../../lib/api";

import { LoginLocaleSwitcher } from "./locale-switcher";

type Step = "phone" | "otp" | "handle" | "language";

const RESEND_SECONDS = 30; // mirrors otp_limits' first-rung resend cooldown

/** The rail in the A2 reference is not decoration - it is THIS array. The
 * flow has always had four steps; the screen simply never said so, which is
 * why "enter your number" felt open-ended on the one screen where a farmer is
 * deciding whether to trust us at all. Order matters: it is the order
 * `finish()` walks. */
const STEP_ORDER: Step[] = ["phone", "otp", "handle", "language"];

function safeNext(raw: string | undefined): string | null {
  // resume only ever returns to our own /authorize - anything else is dropped
  return raw && raw.startsWith("/authorize?") ? raw : null;
}

export function LoginFlow({
  searchParamsPromise,
}: {
  searchParamsPromise: Promise<{ next?: string; ref?: string }>;
}) {
  const { next, ref } = use(searchParamsPromise);
  const t = useTranslations("ui.auth");
  const router = useRouter();

  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [gated, setGated] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [handle, setHandle] = useState("");
  const [handleState, setHandleState] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const verifying = useRef(false);

  const coolingDown = cooldown > 0;
  useEffect(() => {
    if (!coolingDown) return;
    const timer = setInterval(() => setCooldown((s) => s - 1), 1000);
    return () => clearInterval(timer);
  }, [coolingDown]);

  const finish = (nextStep: Step | "done") => {
    if (nextStep !== "done") {
      setStep(nextStep);
      return;
    }
    const resume = safeNext(next);
    if (resume) window.location.assign(resume);
    else router.push("/devices");
  };

  const requestOtp = async () => {
    setBusy(true);
    setError(null);
    try {
      await postJson("/auth/otp/request", { phone, purpose: "login" });
      setCode("");
      setCooldown(RESEND_SECONDS);
      setStep("otp");
    } catch (err) {
      // 503 signup_unavailable is the D30 launch gate, not a user mistake:
      // show the explanation instead of "enter a valid mobile number", which
      // would send people round the same failing loop retyping a fine number.
      if (err instanceof ApiError && err.status === 503 && err.detail === "signup_unavailable") {
        setGated(true);
        return;
      }
      setError(
        err instanceof ApiError && err.status === 429 ? t("otp.locked") : t("phone.invalid"),
      );
    } finally {
      setBusy(false);
    }
  };

  const verifyAndLogin = async (fullCode: string) => {
    if (verifying.current) return;
    verifying.current = true;
    setBusy(true);
    setError(null);
    try {
      const verified = await postJson("/auth/otp/verify", {
        phone,
        purpose: "login",
        code: fullCode,
      });
      const login = await postJson("/auth/login", {
        otp_proof: verified.otp_proof,
        ...(ref ? { referral_code: ref } : {}),
      });
      if (login.is_new_user) {
        const suggested = await getJson("/auth/handle/suggest");
        setSuggestions(suggested.suggestions as string[]);
        finish("handle");
      } else {
        finish("done");
      }
    } catch (err) {
      setCode("");
      const locked = err instanceof ApiError && err.status === 429;
      setError(locked ? t("otp.locked") : t("otp.wrong"));
    } finally {
      verifying.current = false;
      setBusy(false);
    }
  };

  const checkHandle = async (candidate: string) => {
    setHandle(candidate);
    if (candidate.length < 4) {
      setHandleState(null);
      return;
    }
    const result = await getJson(`/auth/handle/check?h=${encodeURIComponent(candidate)}`);
    setHandleState(result.ok ? "available" : (result.code as string));
  };

  const saveHandle = async () => {
    setBusy(true);
    try {
      await postJson("/auth/handle", { handle });
      finish("language");
    } catch (err) {
      setHandleState(err instanceof ApiError ? err.detail : "invalid_format");
    } finally {
      setBusy(false);
    }
  };

  const chooseLanguage = async (locale: "en" | "ta" | "hi") => {
    await postJson("/auth/language", { language: locale });
    // a locale code, never a token (agri_sid stays httpOnly)
    document.cookie = `NEXT_LOCALE=${locale}; path=/; max-age=31536000; samesite=lax`;
    finish("done");
    router.refresh();
  };

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[420px] flex-col justify-center gap-4 px-4 py-8">
      {/* AG-A63: pre-auth locale switcher, above every step. The language
          STEP below persists a choice to the ACCOUNT after login; this only
          changes what THIS browser renders, right now, so a Tamil-first user
          never has to read the flow in English to reach that step. */}
      <LoginLocaleSwitcher />

      {/* Brand lockup. This screen is CONSUMED by agri.in, milk.in and
          theorganic.in alike, so it has to say whose login it is and that the
          one account covers all three - otherwise arriving here from a bounce
          looks like being handed off to a stranger. */}
      <div className="flex flex-col items-center gap-1.5 text-center">
        <span
          aria-hidden="true"
          className="flex h-[52px] w-[52px] items-center justify-center rounded-icon bg-brand text-[26px]"
        >
          🌾
        </span>
        <h1 className="font-display text-[19px] font-extrabold leading-tight text-ink">
          {t("brandTitle")}
        </h1>
        <p className="text-[12px] text-muted">{t("brandSites")}</p>
      </div>

      {/* Where you are in the four steps. Hidden while gated: there is no
          progress through a flow that is closed. */}
      {!gated && (
        <ol aria-label={t("stepsLabel")} className="flex items-center gap-1.5">
          {STEP_ORDER.map((name, index) => {
            const current = STEP_ORDER.indexOf(step);
            const done = index < current;
            const here = index === current;
            return (
              <li
                key={name}
                aria-current={here ? "step" : undefined}
                className={`h-1 flex-1 rounded-full ${
                  done || here ? "bg-brand" : "bg-cream-line"
                }`}
              />
            );
          })}
        </ol>
      )}

      <Card className="p-6">
        {/* The D30 launch gate wins over every step: signup is closed until
            DLT approval lands, so there is no partial flow worth showing. */}
        {gated ? (
          <div className="flex flex-col gap-2">
            <h1 className="font-display text-xl font-bold text-ink">{t("gated.title")}</h1>
            <p className="text-sm text-sub">{t("gated.body")}</p>
          </div>
        ) : (
          <>
        {step === "phone" && (
          <form
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              void requestOtp();
            }}
          >
            <h1 className="font-display text-xl font-bold text-ink">{t("phone.title")}</h1>
            <p className="text-sm text-sub">{t("phone.subtitle")}</p>
            <label className="text-sm font-bold text-ink" htmlFor="phone">
              {t("phone.label")}
            </label>
            {/* The +91 sits OUTSIDE the field, as in the reference. Inside it
                is one more thing to delete on a phone keyboard; beside it, the
                field holds exactly the ten digits a person knows by heart. */}
            <div className="flex items-stretch gap-2">
              <span
                aria-hidden="true"
                className="flex min-h-[44px] flex-none items-center rounded-btn border border-line bg-cream px-3 text-lg font-bold text-sub"
              >
                {t("countryCode")}
              </span>
              <input
                id="phone"
                type="tel"
                inputMode="numeric"
                autoComplete="tel"
                maxLength={10}
                value={phone}
                onChange={(event) => setPhone(event.target.value.replace(/\D/g, ""))}
                className="min-h-[44px] w-full min-w-0 rounded-btn border border-line bg-card px-3.5 text-lg font-bold tracking-[.05em] text-ink"
              />
            </div>
            {error && (
              <p role="alert" className="text-sm text-sub">
                {error}
              </p>
            )}
            <Button variant="brand" type="submit" disabled={busy || phone.length !== 10}>
              {t("phone.cta")}
            </Button>
          </form>
        )}

        {step === "otp" && (
          <div className="flex flex-col gap-3">
            <h1 className="font-display text-xl font-bold text-ink">{t("otp.title")}</h1>
            <p className="text-sm text-sub">{t("otp.sentTo", { phone: `+91 ${phone}` })}</p>
            <OtpInput
              value={code}
              onChange={setCode}
              onComplete={(full) => void verifyAndLogin(full)}
              label={t("otp.inputLabel")}
              disabled={busy}
              error={Boolean(error)}
            />
            {error && (
              <p role="alert" className="text-sm text-sub">
                {error}
              </p>
            )}
            {/* An explicit verify, as in the reference. OtpInput still
                auto-submits on the sixth digit - this is for everyone whose
                autofill drops the code in without firing that, and for anyone
                who simply expects a button to press. */}
            <Button
              variant="brand"
              onClick={() => void verifyAndLogin(code)}
              disabled={busy || code.length !== 6}
            >
              {t("otp.verify")}
            </Button>
            <Button
              variant="ghost"
              onClick={() => void requestOtp()}
              disabled={busy || cooldown > 0}
            >
              {cooldown > 0 ? t("otp.resendIn", { seconds: cooldown }) : t("otp.resend")}
            </Button>
            {/* The reference puts this next to Resend, and it earns the space:
                a farmer whose number is on DND simply never receives the SMS,
                and without being told, they retry until the daily cap locks
                them out of their own account. */}
            <p className="text-[11.5px] leading-[1.5] text-muted">{t("otp.dndHint")}</p>
          </div>
        )}

        {step === "handle" && (
          <div className="flex flex-col gap-3">
            <h1 className="font-display text-xl font-bold text-ink">{t("handle.title")}</h1>
            <p className="text-sm text-sub">{t("handle.subtitle")}</p>
            <input
              aria-label={t("handle.title")}
              value={handle}
              placeholder={t("handle.placeholder")}
              onChange={(event) => void checkHandle(event.target.value.toLowerCase())}
              className="min-h-[44px] rounded-btn border border-line bg-card px-3.5 text-lg font-bold text-ink"
            />
            {handleState && (
              <p role="status" className="text-sm text-sub">
                {handleState === "available" && t("handle.available")}
                {handleState === "taken" && t("handle.taken")}
                {handleState === "reserved" && t("handle.reserved")}
                {(handleState === "invalid_format" || handleState === "already_changed") &&
                  t("handle.invalidFormat")}
              </p>
            )}
            <div className="flex flex-wrap gap-1.5" aria-label={t("handle.suggestions")}>
              {suggestions.map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => void checkHandle(name)}
                  className="tap-target rounded-pill border border-line bg-card px-3 py-1.5 text-sm font-bold text-ink"
                >
                  @{name}
                </button>
              ))}
            </div>
            <Button
              variant="brand"
              onClick={() => void saveHandle()}
              disabled={busy || handleState !== "available"}
            >
              {t("handle.save")}
            </Button>
            <Button variant="ghost" onClick={() => finish("language")}>
              {t("handle.skip")}
            </Button>
          </div>
        )}

        {step === "language" && (
          <div className="flex flex-col gap-3">
            <h1 className="font-display text-xl font-bold text-ink">{t("language.title")}</h1>
            <div className="grid grid-cols-3 gap-2">
              <CategoryTile
                icon="🌐"
                label="English"
                vernacular="English"
                tint="sky"
                onClick={() => void chooseLanguage("en")}
              />
              <CategoryTile
                icon="🌾"
                label="Tamil"
                vernacular="தமிழ்"
                tint="leaf"
                onClick={() => void chooseLanguage("ta")}
              />
              <CategoryTile
                icon="🌻"
                label="Hindi"
                vernacular="हिन्दी"
                tint="gold"
                onClick={() => void chooseLanguage("hi")}
              />
            </div>
          </div>
        )}
          </>
        )}
      </Card>

      {/* DPDP notice. Plain text, not links: agri.in has no /terms or /privacy
          route yet, and its own footer renders these as text for the same
          reason. A link that 404s on the consent line of a login screen is
          worse than no link. Wire them up when the pages exist. */}
      <p className="text-center text-[11.5px] leading-[1.55] text-muted">{t("terms")}</p>
    </main>
  );
}
