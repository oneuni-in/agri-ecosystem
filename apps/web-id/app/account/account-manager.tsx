"use client";

/** Progressive profile editor (D11.E). Location is pincode-only: district and
 * state come back from the server, they are never typed here.
 *
 * ID-U1 P7 changed three things about how this page behaves, all of them
 * consistency rather than features:
 *  - ONE save model. Name used to carry a Save button while language,
 *    interests and every toggle applied instantly, so the page taught two
 *    contradictory rules about when a change had taken. Everything is
 *    instant-apply now, with a per-section "Saved ✓" flash.
 *  - The photo renders as a photo. It used to be a bare "✓".
 *  - The completion bar says what is missing and what completing it pays,
 *    instead of a percentage with no next action.
 */

import { Button, Card, PincodeInput, useToast } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { ApiError, getJson, patchJson, postForm, postJson } from "../../lib/api";

import { DpdpBlock } from "./dpdp-block";

export interface ProfileData {
  agri_id: string;
  name: string | null;
  state: string | null;
  district: string | null;
  pincode: string | null;
  language: string | null;
  interests: string[];
  has_avatar: boolean;
  completion_score: number;
  missing: string[];
  visibility: Record<string, boolean>;
  member_since: string;
}

const LANGUAGES = ["en", "ta", "hi"] as const;
const VISIBILITY_KEYS = ["name", "location", "language", "interests", "avatar"] as const;

/** How long after the last keystroke a name edit commits. Long enough not to
 * save half a name, short enough that leaving the page without blurring does
 * not lose the edit. Blur commits immediately regardless. */
const NAME_AUTOSAVE_MS = 900;
const FLASH_MS = 1800;

export function AccountManager({
  initial,
  canChangeHandle,
  profileCoins,
  erasureGraceDays,
}: {
  initial: ProfileData;
  canChangeHandle: boolean;
  erasureGraceDays: number;
  // explicitly `| undefined`: the repo runs exactOptionalPropertyTypes, and
  // "the rules table had no profile_100 row" is a real state this page must
  // be able to receive rather than a missing prop.
  profileCoins?: number | undefined;
}) {
  const t = useTranslations("ui.auth.profile");
  // The handle validation states reuse the LOGIN step's strings, not
  // copies: the same server code must read the same way wherever a
  // handle is checked, or the two surfaces drift into disagreeing about
  // what "reserved" means.
  const th = useTranslations("ui.auth.handle");
  const { toast } = useToast();
  const [profile, setProfile] = useState(initial);
  const [name, setName] = useState(initial.name ?? "");
  const [pincode, setPincode] = useState(initial.pincode ?? "");
  const [interestDraft, setInterestDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [avatarVersion, setAvatarVersion] = useState(0);
  const [handleOpen, setHandleOpen] = useState(false);
  const [handleDraft, setHandleDraft] = useState("");
  const [handleState, setHandleState] = useState<string | null>(null);
  const [handleAllowed, setHandleAllowed] = useState(canChangeHandle);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!flash) return;
    const timer = setTimeout(() => setFlash(null), FLASH_MS);
    return () => clearTimeout(timer);
  }, [flash]);

  const apply = async (payload: Record<string, unknown>, section: string) => {
    setBusy(true);
    try {
      const updated = (await patchJson("/identity/profile", payload)) as unknown as ProfileData;
      setProfile(updated);
      // Success is an inline flash beside the thing that changed, not a toast:
      // a toast for every instant-apply field would fire constantly and never
      // says WHICH field took. Failures still toast — those must interrupt.
      setFlash(section);
    } catch (error) {
      toast({
        title:
          error instanceof ApiError && error.detail === "unknown_pincode"
            ? t("unknownPincode")
            : t("error"),
      });
    } finally {
      setBusy(false);
    }
  };

  // --- name: instant-apply, debounced, and committed on blur ---------------
  const nameTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const commitName = (value: string) => {
    if (nameTimer.current) clearTimeout(nameTimer.current);
    const trimmed = value.trim();
    if (!trimmed || trimmed === (profile.name ?? "")) return;
    void apply({ name: trimmed }, "name");
  };
  const onNameChange = (value: string) => {
    setName(value);
    if (nameTimer.current) clearTimeout(nameTimer.current);
    nameTimer.current = setTimeout(() => commitName(value), NAME_AUTOSAVE_MS);
  };

  const uploadAvatar = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    setBusy(true);
    try {
      const updated = (await postForm("/identity/profile/avatar", form)) as unknown as ProfileData;
      setProfile(updated);
      // the <img> src is a fixed owner-scoped route, so it needs a version
      // bump to stop the browser showing the previous photo from cache
      setAvatarVersion((n) => n + 1);
      setFlash("avatar");
    } catch (error) {
      toast({
        title:
          error instanceof ApiError &&
          (error.detail === "too_large" ||
            error.detail === "unsupported_type" ||
            error.detail === "empty_file")
            ? t("avatarTooLarge")
            : t("error"),
      });
    } finally {
      setBusy(false);
    }
  };

  const addInterest = () => {
    const value = interestDraft.trim();
    if (!value || profile.interests.length >= 10) return;
    if (profile.interests.some((item) => item.toLowerCase() === value.toLowerCase())) {
      setInterestDraft("");
      return;
    }
    setInterestDraft("");
    void apply({ interests: [...profile.interests, value] }, "interests");
  };

  // --- handle: the one change, checked before it is spent ------------------
  const checkHandle = async (candidate: string) => {
    setHandleDraft(candidate);
    if (candidate.length < 4) {
      setHandleState(null);
      return;
    }
    setHandleState("checking");
    try {
      const result = await getJson(`/auth/handle/check?h=${encodeURIComponent(candidate)}`);
      setHandleState(result.ok ? "available" : (result.code as string));
    } catch {
      setHandleState(null);
    }
  };

  const saveHandle = async () => {
    setBusy(true);
    try {
      const saved = await postJson("/auth/handle", { handle: handleDraft });
      setProfile((p) => ({ ...p, agri_id: saved.agri_id as string }));
      // the allowance is spent the moment the server accepts it
      setHandleAllowed(false);
      setHandleOpen(false);
      setFlash("handle");
    } catch (error) {
      setHandleState(error instanceof ApiError ? error.detail : "invalid_format");
    } finally {
      setBusy(false);
    }
  };

  const Saved = ({ section }: { section: string }) =>
    flash === section ? (
      <span role="status" className="text-xs font-bold text-up">
        {t("savedFlash")}
      </span>
    ) : null;

  return (
    <main className="mx-auto max-w-xl space-y-4 p-4">
      <h1 className="text-xl font-bold text-ink">{t("title")}</h1>

      {/* @handle — the one identity field this app owns, and the one the
          shipped page never showed. */}
      <Card className="space-y-2 p-4">
        <div className="flex items-center gap-2">
          <p className="flex-1 text-sm font-semibold text-ink">{t("handleTitle")}</p>
          <Saved section="handle" />
        </div>
        {handleOpen ? (
          <div className="space-y-2">
            <div className="relative">
              <span
                aria-hidden="true"
                className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 font-bold text-muted"
              >
                @
              </span>
              <input
                aria-label={t("handleTitle")}
                value={handleDraft}
                onChange={(event) => void checkHandle(event.target.value.toLowerCase())}
                className="min-h-[44px] w-full rounded-btn border border-line bg-card py-2 pl-8 pr-3.5 font-bold text-ink"
              />
            </div>
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
                {handleState === "checking" && th("checking")}
                {handleState === "available" && th("available", { handle: handleDraft })}
                {handleState === "taken" && th("taken", { handle: handleDraft })}
                {handleState === "reserved" && th("reserved", { handle: handleDraft })}
                {handleState === "invalid_format" && th("invalidFormat")}
                {handleState === "already_changed" && t("handleSpent")}
              </p>
            )}
            <div className="flex gap-2">
              <Button
                variant="brand"
                disabled={busy || handleState !== "available"}
                onClick={() => void saveHandle()}
              >
                {t("handleSave")}
              </Button>
              <Button variant="ghost" onClick={() => setHandleOpen(false)}>
                {t("handleCancel")}
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <p className="flex-1 font-bold text-ink">@{profile.agri_id}</p>
            {handleAllowed && (
              <Button
                variant="ghost"
                className="flex-none"
                onClick={() => {
                  setHandleDraft(profile.agri_id);
                  setHandleState(null);
                  setHandleOpen(true);
                }}
              >
                {t("handleChange")}
              </Button>
            )}
          </div>
        )}
        {/* The rule, in the state it is actually in. A7's card says "you
            haven't used yours" unconditionally, but signup's pick IS the one
            change (set_handle flips agri_id_changed_once), so for most people
            this reads as already spent — which is the truth they need. */}
        <p className="text-sm text-sub">
          {handleAllowed ? t("handleOneEver") : t("handleSpent")}
        </p>
      </Card>

      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-2">
          <p className="flex-1 text-sm font-semibold text-ink">
            {t("completion", { score: profile.completion_score })}
          </p>
          {/* What finishing pays. Amount from the profile_100 rule at render
              time — never a literal. */}
          {profileCoins !== undefined && profile.completion_score < 100 && (
            <span className="rounded-pill bg-coins-bg px-2 py-0.5 text-xs font-bold text-coins-fg">
              🪙 {t("completionReward", { amount: profileCoins })}
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-sub" data-testid="member-since">
          {t("memberSince", {
            date: new Intl.DateTimeFormat("en", { month: "long", year: "numeric" }).format(
              new Date(profile.member_since),
            ),
          })}
        </p>
        <div
          className="mt-2 h-2 rounded-pill bg-line"
          role="progressbar"
          aria-valuenow={profile.completion_score}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="h-2 rounded-pill bg-brand"
            style={{ width: `${profile.completion_score}%` }}
          />
        </div>
        {/* Which parts are still empty, from the SERVER — the same reading
            that produced the percentage, so the two can never disagree. */}
        {profile.missing.length > 0 && (
          <p className="mt-2 text-sm text-sub">
            {t("missingLabel", {
              items: profile.missing
                .filter((part) => part !== "phone_verified")
                .map((part) => t(`missingParts.${part}`))
                .join(", "),
            })}
          </p>
        )}
      </Card>

      <Card className="space-y-2 p-4">
        <div className="flex items-center gap-2">
          <label className="flex-1 text-sm font-semibold text-ink" htmlFor="profile-name">
            {t("name")}
          </label>
          <Saved section="name" />
        </div>
        {/* No Save button: this field saves like every other control on the
            page. Debounced while typing, committed on blur. */}
        <input
          id="profile-name"
          className="min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
          placeholder={t("namePlaceholder")}
          value={name}
          maxLength={80}
          disabled={busy}
          onChange={(event) => onNameChange(event.target.value)}
          onBlur={(event) => commitName(event.target.value)}
        />
      </Card>

      <Card className="space-y-2 p-4">
        <div className="flex items-center gap-2">
          <p className="flex-1 text-sm font-semibold text-ink">{t("location")}</p>
          <Saved section="location" />
        </div>
        <p className="text-sm text-sub">{t("pincodeHint")}</p>
        {/* The pinbox's own "Find" button resolves the pincode (district/state
            come back from the server) — no separate save button needed. */}
        <PincodeInput
          aria-label={t("location")}
          findLabel={t("pincodeFind")}
          value={pincode}
          disabled={busy}
          findDisabled={busy || pincode.length !== 6}
          onFind={() => void apply({ pincode }, "location")}
          onChange={(event) => setPincode(event.target.value)}
        />
        {profile.district ? (
          <p className="text-sm text-sub">
            {profile.district}, {profile.state} {profile.pincode}
          </p>
        ) : null}
      </Card>

      <Card className="space-y-2 p-4">
        <div className="flex items-center gap-2">
          <p className="flex-1 text-sm font-semibold text-ink">{t("language")}</p>
          <Saved section="language" />
        </div>
        <div className="flex gap-2">
          {LANGUAGES.map((lang) => (
            <Button
              key={lang}
              variant={profile.language === lang ? "brand" : "ghost"}
              disabled={busy}
              onClick={() => void apply({ language: lang }, "language")}
            >
              {lang.toUpperCase()}
            </Button>
          ))}
        </div>
      </Card>

      <Card className="space-y-2 p-4">
        <div className="flex items-center gap-2">
          <p className="flex-1 text-sm font-semibold text-ink">{t("interests")}</p>
          <Saved section="interests" />
        </div>
        {/* What interests DO. The shipped hint said only how many you may add,
            which answers a question nobody was asking. */}
        <p className="text-sm text-sub">{t("interestsExplainer")}</p>
        <p className="text-sm text-sub">{t("interestsHint")}</p>
        <div className="flex flex-wrap gap-2">
          {profile.interests.map((interest) => (
            <button
              key={interest}
              type="button"
              className="tap-target rounded-pill border border-line px-3 py-1 text-sm text-ink disabled:opacity-50"
              aria-label={t("removeInterest", { interest })}
              disabled={busy || profile.interests.length <= 1}
              onClick={() =>
                void apply(
                  { interests: profile.interests.filter((item) => item !== interest) },
                  "interests",
                )
              }
            >
              {interest} ✕
            </button>
          ))}
        </div>
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            addInterest();
          }}
        >
          <input
            className="min-h-[44px] min-w-0 flex-1 rounded-btn border border-line bg-card px-3 py-2 text-ink"
            placeholder={t("interestPlaceholder")}
            aria-label={t("interests")}
            value={interestDraft}
            maxLength={40}
            onChange={(event) => setInterestDraft(event.target.value)}
          />
          <Button type="submit" disabled={busy || profile.interests.length >= 10}>
            {t("addInterest")}
          </Button>
        </form>
      </Card>

      <Card className="space-y-2 p-4">
        <div className="flex items-center gap-2">
          <p className="flex-1 text-sm font-semibold text-ink">{t("avatar")}</p>
          <Saved section="avatar" />
        </div>
        <div className="flex items-center gap-3">
          {/* A photo, not a tick. Served by an owner-scoped API route rather
              than a public media URL, so the visibility switch below keeps
              governing who can FETCH the image and not merely who is shown a
              link to it. */}
          {profile.has_avatar ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={`/api/id/identity/profile/avatar?v=${avatarVersion}`}
              alt={t("avatarAlt")}
              width={56}
              height={56}
              className="h-14 w-14 flex-none rounded-full border border-line object-cover"
            />
          ) : null}
          <Button
            variant="ghost"
            className="flex-none"
            disabled={busy}
            onClick={() => fileInputRef.current?.click()}
          >
            {t("avatarUpload")}
          </Button>
        </div>
        {/* Native file inputs render unstyled OS chrome that can't be sized to
            the 44px rule or kept token-only - hidden behind the Button above,
            which already meets both. */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void uploadAvatar(file);
            event.target.value = "";
          }}
        />
      </Card>

      <Card className="space-y-2 p-4">
        <div className="flex items-center gap-2">
          <p className="flex-1 text-sm font-semibold text-ink">{t("visibility")}</p>
          <Saved section="visibility" />
        </div>
        <p className="text-sm text-sub">{t("visibilityHint")}</p>
        {VISIBILITY_KEYS.map((key) => (
          <div key={key}>
            <label className="flex min-h-[44px] w-full items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                className="h-5 w-5 accent-brand"
                checked={profile.visibility[key] ?? false}
                disabled={busy}
                onChange={(event) =>
                  void apply({ visibility: { [key]: event.target.checked } }, "visibility")
                }
              />
              {t(`visibilityKeys.${key}`)}
            </label>
            {/* "Location" without saying how much of it is the difference
                between a district and a doorstep. */}
            {key === "location" && (
              <p className="ml-7 -mt-1 text-xs text-muted">{t("visibilityLocationHint")}</p>
            )}
          </div>
        ))}
      </Card>

      {/* DPDP rights, last: they are the least-used part of the page and
          the most consequential, so they sit below everything a person came
          here to edit rather than beside it. */}
      <DpdpBlock graceDays={erasureGraceDays} />

      <a href="/devices" className="inline-block text-sm text-brand underline">
        {t("devices")}
      </a>
    </main>
  );
}
