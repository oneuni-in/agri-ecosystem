"use client";

import { Button, Card, CategoryTile, OtpInput } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { use, useEffect, useRef, useState } from "react";

import { ApiError, getJson, postJson } from "../../lib/api";

type Step = "phone" | "otp" | "handle" | "language";

const RESEND_SECONDS = 30; // mirrors otp_limits' first-rung resend cooldown

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
            <input
              id="phone"
              type="tel"
              inputMode="numeric"
              autoComplete="tel"
              maxLength={10}
              value={phone}
              onChange={(event) => setPhone(event.target.value.replace(/\D/g, ""))}
              className="min-h-[44px] rounded-btn border border-line bg-card px-3.5 text-lg font-bold tracking-[.05em] text-ink"
            />
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
            <Button
              variant="ghost"
              onClick={() => void requestOtp()}
              disabled={busy || cooldown > 0}
            >
              {cooldown > 0 ? t("otp.resendIn", { seconds: cooldown }) : t("otp.resend")}
            </Button>
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
    </main>
  );
}
