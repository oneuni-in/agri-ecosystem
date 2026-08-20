"use client";

import { Button, Card, CategoryTile, OtpInput } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { use, useEffect, useRef, useState } from "react";

import { ApiError, getJson, postJson } from "../../lib/api";
import {
  RULE_REFEREE,
  RULE_REFERRER,
  RULE_SIGNUP,
  type RuleAmounts,
} from "../../lib/coins";

import { LoginLocaleSwitcher } from "./locale-switcher";

type Step = "phone" | "otp" | "handle" | "language" | "done";

/** How long the done screen waits before taking the farmer where they were
 * already going. Long enough to read the reward line, short enough that a
 * phone put down mid-signup still lands somewhere useful. */
const DONE_AUTO_CONTINUE_SECONDS = 6;

const RESEND_SECONDS = 30; // mirrors otp_limits' first-rung resend cooldown

/** The rail in the A2 reference is not decoration - it is THIS array. The
 * flow has always had four steps; the screen simply never said so, which is
 * why "enter your number" felt open-ended on the one screen where a farmer is
 * deciding whether to trust us at all. Order matters: it is the order
 * `finish()` walks. */
const STEP_ORDER: Step[] = ["phone", "otp", "handle", "language"];

/** The reference's masked form: enough of the number to recognise it as
 * yours, not enough for someone reading over a shoulder to write down. */
function maskPhone(digits: string): string {
  if (digits.length !== 10) return "";
  return `+91 ${digits.slice(0, 2)}\u2022\u2022\u2022\u2022\u2022\u2022${digits.slice(-2)}`;
}

const SITES = [
  { host: "agri.in", icon: "\ud83c\udf3e", tagKey: "done.agriTag" },
  { host: "milk.in", icon: "\ud83e\udd5b", tagKey: "done.milkTag" },
  { host: "theorganic.in", icon: "\ud83c\udf3f", tagKey: "done.organicTag" },
] as const;

/** The rate-limit message, naming the real wait when the server sent one.
 *
 * The throttles always send Retry-After; before ID-U1 the client dropped it
 * and the copy said "request a new code" - the one action the throttle had
 * just refused.
 *
 * The unit matters as much as the number. These windows are not all small:
 * the resend cooldown is 30 s but the per-phone daily cap is a full 24 h, and
 * "wait about 1440 minutes" is not something a person can act on. Anything an
 * hour or longer is said in hours. Rounded UP throughout - telling someone to
 * wait 13 when the window is 13.4 just sends them back for a second refusal.
 */
function lockedMessage(
  err: ApiError,
  t: (key: string, values?: Record<string, string | number>) => string,
): string {
  if (err.retryAfter === null) return t("otp.locked");
  if (err.retryAfter >= 3600) {
    return t("otp.lockedForHours", { hours: Math.ceil(err.retryAfter / 3600) });
  }
  return t("otp.lockedFor", { minutes: Math.max(1, Math.ceil(err.retryAfter / 60)) });
}

function safeNext(raw: string | undefined): string | null {
  // resume only ever returns to our own /authorize - anything else is dropped
  return raw && raw.startsWith("/authorize?") ? raw : null;
}

export function LoginFlow({
  searchParamsPromise,
  ruleAmounts,
}: {
  searchParamsPromise: Promise<{ next?: string; ref?: string }>;
  ruleAmounts: RuleAmounts;
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
  const [agriId, setAgriId] = useState<string | null>(null);
  const [isNewUser, setIsNewUser] = useState(false);
  const [inviter, setInviter] = useState<string | null>(null);
  const [autoIn, setAutoIn] = useState(DONE_AUTO_CONTINUE_SECONDS);
  const verifying = useRef(false);

  // The banner exists to name a reward, so it renders only when it can name
  // BOTH halves. A partial banner ("you get some coins") is worse than none,
  // and a hardcoded fallback is the thing this pass is forbidden to do.
  const refereeCoins = ruleAmounts[RULE_REFEREE];
  const referrerCoins = ruleAmounts[RULE_REFERRER];
  const signupCoins = ruleAmounts[RULE_SIGNUP];
  const showReferral = Boolean(ref) && refereeCoins !== undefined && referrerCoins !== undefined;

  // Name the inviter only now, with a session in hand. /coins/referral/resolve
  // is private precisely so this cannot happen on the phone step. Best-effort:
  // no name simply means no line.
  const onDone = step === "done";
  useEffect(() => {
    if (!onDone || !ref) return;
    let cancelled = false;
    void (async () => {
      try {
        const body = await getJson(
          `/coins/referral/resolve?code=${encodeURIComponent(ref)}`,
        );
        if (!cancelled) setInviter((body.handle as string | null) ?? null);
      } catch {
        if (!cancelled) setInviter(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [onDone, ref]);

  const coolingDown = cooldown > 0;
  useEffect(() => {
    if (!coolingDown) return;
    const timer = setInterval(() => setCooldown((s) => s - 1), 1000);
    return () => clearInterval(timer);
  }, [coolingDown]);

  /** The redirect this flow has always performed, lifted out of finish()
   * UNCHANGED so the done screen's button and its auto-continue both land
   * exactly where the flow used to go on its own: same safeNext check, same
   * /devices fallback. */
  const performRedirect = () => {
    const resume = safeNext(next);
    if (resume) window.location.assign(resume);
    else router.push("/devices");
  };

  const finish = (nextStep: Step) => setStep(nextStep);

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
        err instanceof ApiError && err.status === 429
          ? lockedMessage(err, t)
          : t("phone.invalid"),
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
      setAgriId(login.agri_id as string);
      setIsNewUser(Boolean(login.is_new_user));
      if (login.is_new_user) {
        const suggested = await getJson("/auth/handle/suggest");
        setSuggestions(suggested.suggestions as string[]);
        finish("handle");
      } else {
        // The done screen announces a SIGNUP. A returning login has no
        // reward to name, so it goes where it was always going rather
        // than paying an interstitial on every sign-in.
        performRedirect();
      }
    } catch (err) {
      setCode("");
      const locked = err instanceof ApiError && err.status === 429;
      setError(locked ? lockedMessage(err as ApiError, t) : t("otp.wrong"));
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
    // "checking" is the fifth state the A7 reference names, and the only one
    // with no server code behind it - it is the window while /auth/handle/check
    // is in flight. Without it the line under the field simply held the PREVIOUS
    // verdict while a new one was being fetched, so a taken handle still read
    // "available" for as long as the request took.
    setHandleState("checking");
    const result = await getJson(`/auth/handle/check?h=${encodeURIComponent(candidate)}`);
    setHandleState(result.ok ? "available" : (result.code as string));
  };

  const saveHandle = async () => {
    setBusy(true);
    try {
      const saved = await postJson("/auth/handle", { handle });
      setAgriId(saved.agri_id as string);
      finish("language");
    } catch (err) {
      setHandleState(err instanceof ApiError ? err.detail : "invalid_format");
    } finally {
      setBusy(false);
    }
  };

  // Auto-continue: a farmer who puts the phone down mid-signup still lands
  // where they were going. Shown as a countdown ON the button, never a silent
  // hijack - and pressing it skips the wait.
  useEffect(() => {
    if (!onDone) return;
    if (autoIn <= 0) {
      performRedirect();
      return;
    }
    const timer = setTimeout(() => setAutoIn((n) => n - 1), 1000);
    return () => clearTimeout(timer);
  }, [onDone, autoIn]);

  const chooseLanguage = async (locale: "en" | "ta" | "hi") => {
    await postJson("/auth/language", { language: locale });
    // a locale code, never a token (agri_sid stays httpOnly)
    document.cookie = `NEXT_LOCALE=${locale}; path=/; max-age=31536000; samesite=lax`;
    finish("done");
    router.refresh();
  };

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[540px] flex-col items-center justify-center gap-4 px-4 py-8">
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
      {/* The rail measures the four SIGNUP steps. "done" is past all of them,
          so it hides rather than rendering four bars with nothing current —
          the reference hides it on this screen for the same reason. */}
      {!gated && step !== "done" && (
        <ol
          aria-label={t("stepsLabel")}
          className="flex w-full max-w-[420px] items-center gap-1.5"
        >
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

      <Card className="w-full max-w-[420px] p-6">
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
            {/* Referral banner. `?ref=` has always been captured and passed to
                /auth/login as referral_code; until now it was invisible, so an
                invitation that promised coins arrived at a screen mentioning
                none. Deliberately UNNAMED here: resolving a code to the
                inviter's handle before sign-in would publish a code -> handle
                oracle on a public route. The name arrives on the done screen,
                once there is a session to gate it behind.

                The TIMING in the copy is the engine's, not the mockup's. A7
                says "+100 when you sign up"; referrals.py delays BOTH rewards
                to the referee's profile_100 event on purpose - that delay is
                the anti-farm design. Promising coins at signup would promise
                something no code path pays. */}
            {showReferral && (
              <div className="flex items-start gap-2.5 rounded-btn border border-line bg-brand-soft px-3 py-2.5">
                <span aria-hidden="true" className="text-[18px] leading-none">
                  🎁
                </span>
                <p className="text-[12.5px] leading-[1.5] text-brand-deep">
                  <b className="font-bold">{t("referral.title")}</b>{" "}
                  {t("referral.body", { referee: refereeCoins, referrer: referrerCoins })}
                </p>
              </div>
            )}
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
            {/* DPDP consent, one sentence, no checkbox. It replaces the generic
                "you agree to our Terms and Privacy policy" line that used to
                sit below the card: boilerplate nobody reads is not consent,
                and the A7 ADD asks for what we store and what we never do, in
                plain words.

                ON THE WORDING: the reference says "we store your number
                ENCRYPTED". identity.users.phone is a plain Text column - it is
                NOT encrypted at rest - so that claim is absent here. A false
                privacy promise on the consent line of a DPDP launch gate is
                not a copy nit. Encrypting the column is a real backlog item;
                until it exists this says only what is true. */}
            <p className="text-[11.5px] leading-[1.55] text-muted">
              {t("phone.dpdp")}{" "}
              <a className="text-brand underline" href="/privacy">
                {t("phone.dpdpLink")}
              </a>
            </p>
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
            {/* The rules sit BESIDE the label, not in an error you have to earn
                by breaking them: "4-20 · a-z 0-9 _" read before typing costs
                nothing, and read after a rejection costs a retry. */}
            <div className="flex items-baseline justify-between gap-2">
              <label className="text-sm font-bold text-ink" htmlFor="handle">
                {t("handle.label")}
              </label>
              <span className="text-[11.5px] text-muted">{t("handle.rules")}</span>
            </div>
            {/* The @ is rendered, never typed: handles.py normalizes a leading
                @ away anyway, so showing it here just tells the truth about
                what the name will look like everywhere else. */}
            <div className="relative">
              {/* Positioned INSIDE the field, as the reference builds it, not
                  as a sibling box: the focus ring is the design system's
                  "never remove" 3px accent outline and it belongs to the
                  input. A wrapped layout let that ring paint straight over
                  the @, cutting the glyph in half whenever the field had
                  focus. */}
              <span
                aria-hidden="true"
                className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-lg font-bold text-muted"
              >
                @
              </span>
              <input
                id="handle"
                value={handle}
                placeholder={t("handle.placeholder")}
                onChange={(event) => void checkHandle(event.target.value.toLowerCase())}
                className="min-h-[44px] w-full min-w-0 rounded-btn border border-line bg-card py-2 pl-8 pr-3.5 text-lg font-bold text-ink"
              />
            </div>
            {/* Five states, each pinned to what the server actually answered.
                `reserved` says only "reserved" - never why, never what else is
                on the list: the blocklist is a brand-squatting defence and
                enumerating it defeats it. */}
            {handleState && (
              <p
                role="status"
                className={`text-sm ${
                  handleState === "available"
                    ? "text-up"
                    : handleState === "checking"
                      ? "text-muted"
                      : "text-down"
                }`}
              >
                {handleState === "checking" && t("handle.checking")}
                {handleState === "available" && t("handle.available", { handle })}
                {handleState === "taken" && t("handle.taken", { handle })}
                {handleState === "reserved" && t("handle.reserved", { handle })}
                {(handleState === "invalid_format" || handleState === "already_changed") &&
                  t("handle.invalidFormat")}
              </p>
            )}
            {/* Suggestions are an ANSWER to a rejection - the taken message
                ends "try one of these:" and these are the these. Under an
                available handle they contradicted the line above them,
                offering alternatives to a name the farmer had just been told
                they could have. */}
            <div
              className={`flex flex-wrap gap-1.5 ${handleState === "available" ? "hidden" : ""}`}
              aria-label={t("handle.suggestions")}
            >
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
            {/* Stated HERE, at pick time, because this pick IS the one change:
                set_handle flips agri_id_changed_once, so a farmer who chooses
                carelessly now has already spent the allowance. Saying it on
                /account afterwards would be telling someone about a door that
                has already shut. */}
            <p className="text-[11.5px] leading-[1.55] text-muted">{t("handle.oneChange")}</p>
          </div>
        )}

        {step === "done" && (
          <div className="flex flex-col gap-3">
            {/* motion-reduce keeps the burst at its FINAL state - visible,
                full size - rather than removing it. The A-U1 contract:
                reduced motion means no animation, never missing content. */}
            <span
              aria-hidden="true"
              className="mx-auto flex h-16 w-16 animate-pop items-center justify-center rounded-full bg-brand-soft text-[30px] motion-reduce:animate-none"
            >
              ✅
            </span>
            <h1 className="text-center font-display text-xl font-bold text-ink">
              {isNewUser ? t("done.title") : t("done.titleReturning")}
            </h1>
            <p className="text-center text-sm text-sub">
              {agriId ? `@${agriId} \u00b7 ` : ""}
              {maskPhone(phone)}
            </p>
            {inviter && (
              <p className="text-center text-[12.5px] text-brand-deep">
                {t("done.invitedBy", { handle: inviter })}
              </p>
            )}
            {/* Signup coins only for an actual signup: a returning login has
                no bonus to announce, and saying otherwise would promise coins
                the ledger will never pay. Amount from the rules table, or the
                line is absent entirely. */}
            {isNewUser && signupCoins !== undefined && (
              <div className="flex items-center gap-2.5 rounded-btn border border-alert-line bg-coins-bg px-3 py-2.5">
                <span aria-hidden="true" className="text-[22px]">
                  🪙
                </span>
                <div>
                  <b className="font-display text-lg text-coins-fg">
                    {t("done.coinsAmount", { amount: signupCoins })}
                  </b>
                  <p className="text-[11px] leading-[1.4] text-sub">{t("done.coinsNote")}</p>
                </div>
              </div>
            )}
            <ul aria-label={t("done.sitesLabel")} className="grid grid-cols-3 gap-2">
              {SITES.map((site) => (
                <li
                  key={site.host}
                  className="rounded-btn border border-line bg-cream px-1.5 py-2.5 text-center"
                >
                  <b className="block text-[12.5px] text-ink">
                    {site.icon} {site.host}
                  </b>
                  {/* break-words is load-bearing, not defensive: Tamil and
                      Hindi taglines are single long words with no break
                      opportunity, and at 390 they ran straight over the card
                      border into the neighbouring tile. */}
                  <span className="block break-words text-[11px] leading-[1.3] text-muted">
                    {t(site.tagKey)}
                  </span>
                </li>
              ))}
            </ul>
            <Button variant="brand" onClick={performRedirect}>
              {autoIn > 0 ? t("done.continueIn", { seconds: autoIn }) : t("done.continue")}
            </Button>
          </div>
        )}

        {step === "language" && (
          <div className="flex flex-col gap-3">
            <h1 className="font-display text-xl font-bold text-ink">{t("language.title")}</h1>
            {/* This step commits on tap - no selected state, no confirm -
                so the only thing that can tell a farmer who mistapped that
                the decision is reversible is this sentence. */}
            <p className="text-sm text-sub">{t("language.subtitle")}</p>
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

      {/* Trust strip. Four facts a farmer deciding whether to hand over a
          phone number is actually weighing, and all four are true today. It
          takes the place of the old generic terms line, whose job (the DPDP
          link) moved INTO the card, under the CTA, where consent belongs.
          Hidden while gated: "free forever" under a closed sign-up reads as
          an advertisement for something you cannot have. */}
      {!gated && (
        <ul className="flex w-full flex-wrap items-center justify-center gap-x-3.5 gap-y-1.5 text-[11px] text-muted">
          {[t("trust.free"), t("trust.noCharges"), t("trust.languages"), t("trust.dpdp")].map(
            (fact) => (
              <li key={fact} className="flex items-center gap-1.5">
                <span aria-hidden="true" className="text-up">
                  ✓
                </span>
                {fact}
              </li>
            ),
          )}
        </ul>
      )}
    </main>
  );
}
