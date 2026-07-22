"use client";

/** Progressive profile editor (D11.E). Location is pincode-only: district and
 * state come back from the server, they are never typed here. */

import { Button, Card, PincodeInput, useToast } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { ApiError, patchJson, postForm } from "../../lib/api";

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
  visibility: Record<string, boolean>;
}

const LANGUAGES = ["en", "ta", "hi"] as const;
const VISIBILITY_KEYS = ["name", "location", "language", "interests", "avatar"] as const;

export function AccountManager({ initial }: { initial: ProfileData }) {
  const t = useTranslations("ui.auth.profile");
  const { toast } = useToast();
  const [profile, setProfile] = useState(initial);
  const [name, setName] = useState(initial.name ?? "");
  const [pincode, setPincode] = useState(initial.pincode ?? "");
  const [interestDraft, setInterestDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const apply = async (payload: Record<string, unknown>, okToast = t("saved")) => {
    setBusy(true);
    try {
      const updated = (await patchJson("/identity/profile", payload)) as unknown as ProfileData;
      setProfile(updated);
      toast({ title: okToast });
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

  const uploadAvatar = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    setBusy(true);
    try {
      const updated = (await postForm("/identity/profile/avatar", form)) as unknown as ProfileData;
      setProfile(updated);
      toast({ title: t("saved") });
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
    void apply({ interests: [...profile.interests, value] });
  };

  return (
    <main className="mx-auto max-w-xl space-y-4 p-4">
      <h1 className="text-xl font-bold text-ink">{t("title")}</h1>

      <Card className="p-4">
        <p className="text-sm font-semibold text-ink">
          {t("completion", { score: profile.completion_score })}
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
      </Card>

      <Card className="space-y-2 p-4">
        <label className="text-sm font-semibold text-ink" htmlFor="profile-name">
          {t("name")}
        </label>
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim()) void apply({ name });
          }}
        >
          <input
            id="profile-name"
            className="min-h-[44px] min-w-0 flex-1 rounded-btn border border-line bg-card px-3 py-2 text-ink"
            placeholder={t("namePlaceholder")}
            value={name}
            maxLength={80}
            onChange={(event) => setName(event.target.value)}
          />
          <Button type="submit" variant="brand" disabled={busy || !name.trim()}>
            {t("save")}
          </Button>
        </form>
      </Card>

      <Card className="space-y-2 p-4">
        <p className="text-sm font-semibold text-ink">{t("location")}</p>
        <p className="text-sm text-sub">{t("pincodeHint")}</p>
        {/* The pinbox's own "Find" button resolves the pincode (district/state
            come back from the server) — no separate save button needed. */}
        <PincodeInput
          aria-label={t("location")}
          findLabel={t("pincodeFind")}
          value={pincode}
          disabled={busy}
          findDisabled={busy || pincode.length !== 6}
          onFind={() => void apply({ pincode })}
          onChange={(event) => setPincode(event.target.value)}
        />
        {profile.district ? (
          <p className="text-sm text-sub">
            {profile.district}, {profile.state} {profile.pincode}
          </p>
        ) : null}
      </Card>

      <Card className="space-y-2 p-4">
        <p className="text-sm font-semibold text-ink">{t("language")}</p>
        <div className="flex gap-2">
          {LANGUAGES.map((lang) => (
            <Button
              key={lang}
              variant={profile.language === lang ? "brand" : "ghost"}
              disabled={busy}
              onClick={() => void apply({ language: lang })}
            >
              {lang.toUpperCase()}
            </Button>
          ))}
        </div>
      </Card>

      <Card className="space-y-2 p-4">
        <p className="text-sm font-semibold text-ink">{t("interests")}</p>
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
                void apply({ interests: profile.interests.filter((item) => item !== interest) })
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
        <p className="text-sm font-semibold text-ink">{t("avatar")}</p>
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            className="flex-none"
            disabled={busy}
            onClick={() => fileInputRef.current?.click()}
          >
            {t("avatarUpload")}
          </Button>
          {profile.has_avatar ? (
            <span aria-hidden="true" className="text-sub">
              ✓
            </span>
          ) : null}
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
        <p className="text-sm font-semibold text-ink">{t("visibility")}</p>
        <p className="text-sm text-sub">{t("visibilityHint")}</p>
        {VISIBILITY_KEYS.map((key) => (
          <label key={key} className="flex min-h-[44px] w-full items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              className="h-5 w-5 accent-brand"
              checked={profile.visibility[key] ?? false}
              disabled={busy}
              onChange={(event) => void apply({ visibility: { [key]: event.target.checked } })}
            />
            {t(`visibilityKeys.${key}`)}
          </label>
        ))}
      </Card>

      <a href="/devices" className="inline-block text-sm text-brand underline">
        {t("devices")}
      </a>
    </main>
  );
}
