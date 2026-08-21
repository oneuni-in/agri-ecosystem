"use client";

/**
 * "What describes you?" (ID-U1 W5).
 *
 * Two answers, two completely different treatments, and that asymmetry is the
 * whole design:
 *
 *  - A FARMER answers here. There is one farm and all three sites read it —
 *    cattle feed milk.in, crops feed agri.in's advisories, certification feeds
 *    theorganic.in — so it belongs on the identity profile rather than being
 *    asked three times by three verticals.
 *  - A BUSINESS answers nowhere near here. Category, timings, photos, GST and
 *    verification belong to the directory listing, where customers see them
 *    and where the claim flow already verifies them. This section collects
 *    nothing about a shop; it routes.
 *
 * You can be both. The reference is explicit about it and so is the model:
 * `describes` is a list, and picking both shows both.
 */

import { Button, Card } from "@agri/ui";
import { useTranslations } from "next-intl";


import { listingsHref } from "../../lib/console";

export interface FarmData {
  land_area: string | null;
  land_unit: string | null;
  tenure: string | null;
  cattle: number | null;
  goats: number | null;
  poultry: number | null;
  irrigation: string | null;
}

const ROLES = [
  { value: "farmer", labelKey: "roleFarmer" },
  { value: "business", labelKey: "roleBusiness" },
  { value: "exploring", labelKey: "roleExploring" },
] as const;

const TENURES = [
  { value: "owned", labelKey: "tenureOwned" },
  { value: "leased", labelKey: "tenureLeased" },
  { value: "both", labelKey: "tenureBoth" },
] as const;

const IRRIGATION = [
  { value: "borewell", labelKey: "irrigationBorewell" },
  { value: "canal", labelKey: "irrigationCanal" },
  { value: "rainfed", labelKey: "irrigationRainfed" },
] as const;

const LIVESTOCK = [
  { field: "cattle", labelKey: "farmCattle", unlocksKey: "farmCattleUnlocks" },
  { field: "goats", labelKey: "farmGoats", unlocksKey: "farmGoatsUnlocks" },
  { field: "poultry", labelKey: "farmPoultry", unlocksKey: "farmPoultryUnlocks" },
] as const;

export function DescribesBlock({
  describes,
  farm,
  ownedBusinesses,
  consoleUrl,
  onSave,
  busy,
  savedFlash,
}: {
  describes: string[];
  farm: FarmData | null;
  ownedBusinesses: string[];
  consoleUrl: string;
  onSave: (payload: Record<string, unknown>) => void;
  busy: boolean;
  savedFlash: React.ReactNode;
}) {
  const t = useTranslations("ui.auth.profile");

  const chosen = new Set(describes);
  const isFarmer = chosen.has("farmer");
  const isBusiness = chosen.has("business");
  const isExploring = chosen.has("exploring");

  const toggleRole = (value: string) => {
    // "just exploring" is the answer "neither", so it replaces rather than
    // joins — the same rule the server enforces.
    if (value === "exploring") {
      onSave({ describes: chosen.has("exploring") ? [] : ["exploring"] });
      return;
    }
    const next = new Set(chosen);
    next.delete("exploring");
    if (next.has(value)) next.delete(value);
    else next.add(value);
    onSave({ describes: [...next] });
  };

  const setFarm = (patch: Record<string, unknown>) => onSave({ farm: patch });

  const count = (field: (typeof LIVESTOCK)[number]["field"]): number =>
    (farm?.[field] as number | null) ?? 0;

  const step = (field: (typeof LIVESTOCK)[number]["field"], delta: number) => {
    const next = Math.max(0, count(field) + delta);
    setFarm({ [field]: next });
  };

  return (
    <Card className="space-y-3 border-alert-line bg-trust-bg p-4">
      <div className="flex items-center gap-2">
        <p className="flex-1 text-sm font-semibold text-ink">{t("describesTitle")}</p>
        {savedFlash}
      </div>
      <p className="text-sm text-sub">{t("describesHint")}</p>

      <div className="flex flex-wrap gap-2">
        {ROLES.map((role) => {
          const on = chosen.has(role.value);
          return (
            <button
              key={role.value}
              type="button"
              aria-pressed={on}
              disabled={busy}
              onClick={() => toggleRole(role.value)}
              className={`tap-target rounded-pill border px-3 py-1.5 text-sm ${
                on ? "border-brand bg-brand-soft font-bold text-brand-deep" : "border-line bg-card text-ink"
              }`}
            >
              {t(role.labelKey)}
            </button>
          );
        })}
      </div>

      {isFarmer && (
        <div className="space-y-3 border-t border-line pt-3">
          <p className="text-sm text-sub">{t("farmIntro")}</p>

          {/* Land. A number without a unit is not actionable — a per-hectare
              scheme threshold cannot read "3.5" — so the unit sits beside it
              and the server assumes acres rather than storing half an answer. */}
          <div className="space-y-1">
            <p className="text-sm font-semibold text-ink">{t("farmLand")}</p>
            <p className="text-xs text-muted">{t("farmLandUnlocks")}</p>
            <div className="flex gap-2">
              <input
                aria-label={t("farmLand")}
                inputMode="decimal"
                defaultValue={farm?.land_area ?? ""}
                disabled={busy}
                onBlur={(event) => {
                  const raw = event.target.value.trim();
                  setFarm({ land_area: raw === "" ? null : raw });
                }}
                className="min-h-[44px] w-24 rounded-btn border border-line bg-card px-3 text-ink"
              />
              {/* its own accessible name: two controls both called "Land"
                  are ambiguous to a screen reader, which cannot tell the
                  amount from the unit */}
              <select
                aria-label={t("farmLandUnit")}
                value={farm?.land_unit ?? "acres"}
                disabled={busy}
                onChange={(event) => setFarm({ land_unit: event.target.value })}
                className="min-h-[44px] rounded-btn border border-line bg-card px-2 text-sm text-ink"
              >
                <option value="acres">{t("unitAcres")}</option>
                <option value="hectares">{t("unitHectares")}</option>
              </select>
            </div>
          </div>

          <ChipRow
            label={t("farmTenure")}
            hint={t("farmTenureUnlocks")}
            options={TENURES.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
            selected={farm?.tenure ?? null}
            disabled={busy}
            onPick={(value) => setFarm({ tenure: value })}
          />

          {LIVESTOCK.map((animal) => (
            <div key={animal.field} className="space-y-1">
              <p className="text-sm font-semibold text-ink">{t(animal.labelKey)}</p>
              <p className="text-xs text-muted">{t(animal.unlocksKey)}</p>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  className="flex-none"
                  aria-label={t("farmDecrease", { label: t(animal.labelKey) })}
                  disabled={busy || count(animal.field) === 0}
                  onClick={() => step(animal.field, -1)}
                >
                  −
                </Button>
                {/* the stored value, not a local counter: 0 is a real answer
                    ("I keep none") and null is "I did not say" */}
                <b className="min-w-8 text-center text-ink">
                  {farm?.[animal.field] ?? "—"}
                </b>
                <Button
                  variant="ghost"
                  className="flex-none"
                  aria-label={t("farmIncrease", { label: t(animal.labelKey) })}
                  disabled={busy}
                  onClick={() => step(animal.field, 1)}
                >
                  +
                </Button>
              </div>
            </div>
          ))}

          <ChipRow
            label={t("farmIrrigation")}
            hint={t("farmIrrigationUnlocks")}
            options={IRRIGATION.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
            selected={farm?.irrigation ?? null}
            disabled={busy}
            onPick={(value) => setFarm({ irrigation: value })}
          />

          <p className="text-xs leading-[1.5] text-muted">{t("farmPrivacy")}</p>
        </div>
      )}

      {isBusiness && (
        <div className="space-y-2 border-t border-line pt-3">
          {/* Collects nothing. The directory listing owns shop details and its
              claim flow already verifies them; duplicating any of it here
              would create a second, unverified copy of the same shop. */}
          <p className="text-sm text-sub">{t("bizRouted")}</p>
          <a
            href={listingsHref(consoleUrl)}
            className="tap-target inline-flex min-h-[44px] items-center rounded-btn bg-brand px-4 text-sm font-bold text-white no-underline"
          >
            {t("bizClaim")}
          </a>
          {ownedBusinesses.length > 0 && (
            <p className="text-xs text-muted">
              {t("bizOwned", { names: ownedBusinesses.join(", ") })}
            </p>
          )}
        </div>
      )}

      {isExploring && (
        <p className="border-t border-line pt-3 text-sm text-sub">{t("exploringNote")}</p>
      )}
    </Card>
  );
}

function ChipRow({
  label,
  hint,
  options,
  selected,
  disabled,
  onPick,
}: {
  label: string;
  hint: string;
  options: readonly { value: string; label: string }[];
  selected: string | null;
  disabled: boolean;
  onPick: (value: string) => void;
}) {
  return (
    <div className="space-y-1">
      <p className="text-sm font-semibold text-ink">{label}</p>
      <p className="text-xs text-muted">{hint}</p>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const on = selected === option.value;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={on}
              disabled={disabled}
              onClick={() => onPick(option.value)}
              className={`tap-target rounded-pill border px-3 py-1.5 text-sm ${
                on ? "border-brand bg-brand-soft font-bold text-brand-deep" : "border-line bg-card text-ink"
              }`}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
