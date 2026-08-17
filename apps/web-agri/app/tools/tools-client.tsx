"use client";

/**
 * A-U1 §10c — the four v1 farm calculators (A1 `.tool` card look). One
 * island for the whole grid: the only client concern is input state; every
 * formula is imported from @agri/ui's pure, unit-tested
 * `agri-calculators` module. NO network anywhere — the page keeps working
 * offline once loaded. Results recompute on every change.
 *
 * Inputs keep the 44px hit floor (min-h-[44px]); anchors #emi #seed-rate
 * #fertilizer #spray are the home §10c entry links' targets.
 */
import {
  emi,
  fertilizerPlan,
  NPK_PRESETS_KG_PER_HA,
  SEED_RATE_KG_PER_HA,
  seedRequirementKg,
  SPRAY_VOLUME_L_PER_ACRE,
  sprayMlPerTank,
  tanksPerAcre,
  type NpkCrop,
  type SeedCrop,
} from "@agri/ui";
import { useTranslations } from "next-intl";
import { useId, useState, type ReactNode } from "react";

const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const num = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 });

function parse(v: string): number {
  const n = Number.parseFloat(v);
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

function ToolCard({
  id,
  icon,
  title,
  sub,
  children,
}: {
  id: string;
  icon: string;
  title: string;
  sub: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className="scroll-mt-20 rounded-card border border-cream-line bg-card p-4 transition-shadow hover:shadow-lift"
    >
      <div className="flex items-center gap-2.5">
        <span aria-hidden="true" className="text-xl">
          {icon}
        </span>
        <div>
          <h2 className="text-[13.5px] font-semibold text-ink">{title}</h2>
          <p className="text-[10.5px] text-muted">{sub}</p>
        </div>
      </div>
      <div className="mt-3 flex flex-col gap-2.5">{children}</div>
    </section>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <label htmlFor={id} className="block">
      <span className="mb-1 block text-[11px] font-medium text-sub">{label}</span>
      {children(id)}
    </label>
  );
}

const inputCls =
  "w-full min-h-[44px] rounded-btn border border-cream-line bg-card px-3 text-sm text-ink focus:border-brand focus:outline-none";

function Result({ label, value, testId }: { label: string; value: string; testId: string }) {
  return (
    <p className="rounded-btn bg-brand-soft px-3 py-2.5 text-[12.5px] text-brand-deep">
      {label}{" "}
      <b data-testid={testId} className="font-display text-[17px] font-semibold">
        {value}
      </b>
    </p>
  );
}

/* ── EMI ───────────────────────────────────────────────────────────────── */

function EmiTool() {
  const t = useTranslations("ui.tools.emi");
  const [principal, setPrincipal] = useState("650000");
  const [rate, setRate] = useState("12.5");
  const [months, setMonths] = useState("84");
  const monthly = emi(parse(principal), parse(rate), parse(months));
  const total = monthly * parse(months);
  return (
    <ToolCard id="emi" icon="🚜" title={t("title")} sub={t("sub")}>
      <Field label={t("principal")}>
        {(id) => (
          <input id={id} type="number" inputMode="numeric" min="0" className={inputCls} value={principal} onChange={(e) => setPrincipal(e.target.value)} />
        )}
      </Field>
      <Field label={t("rate")}>
        {(id) => (
          <input id={id} type="number" inputMode="decimal" min="0" step="0.1" className={inputCls} value={rate} onChange={(e) => setRate(e.target.value)} />
        )}
      </Field>
      <Field label={t("months")}>
        {(id) => (
          <input id={id} type="number" inputMode="numeric" min="1" className={inputCls} value={months} onChange={(e) => setMonths(e.target.value)} />
        )}
      </Field>
      <Result label={t("result")} value={`₹${inr.format(monthly)}`} testId="emi-result" />
      {monthly > 0 ? (
        <p className="text-[10.5px] text-muted">
          {t("total", {
            total: `₹${inr.format(total)}`,
            interest: `₹${inr.format(Math.max(0, total - parse(principal)))}`,
          })}
        </p>
      ) : null}
    </ToolCard>
  );
}

/* ── Seed rate ─────────────────────────────────────────────────────────── */

const SEED_CROPS = Object.keys(SEED_RATE_KG_PER_HA) as SeedCrop[];
/** i18n key per preset (kebab-case keys don't fit message paths). */
const SEED_KEY: Record<SeedCrop, string> = {
  "paddy-transplanted": "paddyTransplanted",
  "paddy-direct": "paddyDirect",
  maize: "maize",
  groundnut: "groundnut",
  blackgram: "blackgram",
};

function SeedTool() {
  const t = useTranslations("ui.tools.seed");
  const [crop, setCrop] = useState<SeedCrop>("paddy-transplanted");
  const [acres, setAcres] = useState("1");
  const kg = seedRequirementKg(crop, parse(acres));
  return (
    <ToolCard id="seed-rate" icon="🌱" title={t("title")} sub={t("sub")}>
      <Field label={t("crop")}>
        {(id) => (
          <select id={id} className={inputCls} value={crop} onChange={(e) => setCrop(e.target.value as SeedCrop)}>
            {SEED_CROPS.map((c) => (
              <option key={c} value={c}>
                {t(`crops.${SEED_KEY[c]}`)} · {SEED_RATE_KG_PER_HA[c]} kg/ha
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field label={t("area")}>
        {(id) => (
          <input id={id} type="number" inputMode="decimal" min="0" step="0.5" className={inputCls} value={acres} onChange={(e) => setAcres(e.target.value)} />
        )}
      </Field>
      <Result label={t("result")} value={`${num.format(kg)} kg`} testId="seed-rate-result" />
      <p className="text-[10.5px] text-muted">{t("note")}</p>
    </ToolCard>
  );
}

/* ── Fertilizer dose ───────────────────────────────────────────────────── */

const NPK_CROPS = Object.keys(NPK_PRESETS_KG_PER_HA) as NpkCrop[];

function FertilizerTool() {
  const t = useTranslations("ui.tools.fert");
  const [n, setN] = useState(String(NPK_PRESETS_KG_PER_HA.paddy.n));
  const [p, setP] = useState(String(NPK_PRESETS_KG_PER_HA.paddy.p));
  const [k, setK] = useState(String(NPK_PRESETS_KG_PER_HA.paddy.k));
  const [acres, setAcres] = useState("1");
  const plan = fertilizerPlan({ n: parse(n), p: parse(p), k: parse(k) }, parse(acres));
  const applyPreset = (crop: NpkCrop) => {
    const preset = NPK_PRESETS_KG_PER_HA[crop];
    setN(String(preset.n));
    setP(String(preset.p));
    setK(String(preset.k));
  };
  return (
    <ToolCard id="fertilizer" icon="🧪" title={t("title")} sub={t("sub")}>
      <div className="flex flex-wrap gap-1.5">
        {NPK_CROPS.map((crop) => (
          <button
            key={crop}
            type="button"
            onClick={() => applyPreset(crop)}
            className="inline-flex min-h-[44px] items-center rounded-pill border border-cream-line bg-cream px-3.5 text-[11.5px] font-medium text-ink hover:border-brand"
          >
            {t(`crops.${crop}`)}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Field label={t("n")}>
          {(id) => (
            <input id={id} type="number" inputMode="decimal" min="0" className={inputCls} value={n} onChange={(e) => setN(e.target.value)} />
          )}
        </Field>
        <Field label={t("p")}>
          {(id) => (
            <input id={id} type="number" inputMode="decimal" min="0" className={inputCls} value={p} onChange={(e) => setP(e.target.value)} />
          )}
        </Field>
        <Field label={t("k")}>
          {(id) => (
            <input id={id} type="number" inputMode="decimal" min="0" className={inputCls} value={k} onChange={(e) => setK(e.target.value)} />
          )}
        </Field>
      </div>
      <Field label={t("area")}>
        {(id) => (
          <input id={id} type="number" inputMode="decimal" min="0" step="0.5" className={inputCls} value={acres} onChange={(e) => setAcres(e.target.value)} />
        )}
      </Field>
      <Result
        label={t("result")}
        value={`${t("urea")} ${num.format(plan.urea)} kg · ${t("dap")} ${num.format(plan.dap)} kg · ${t("mop")} ${num.format(plan.mop)} kg`}
        testId="fertilizer-result"
      />
      <p className="text-[10.5px] text-muted">{t("note")}</p>
    </ToolCard>
  );
}

/* ── Spray dilution ────────────────────────────────────────────────────── */

function SprayTool() {
  const t = useTranslations("ui.tools.spray");
  const [dose, setDose] = useState("2");
  const [tank, setTank] = useState("16");
  const perTank = sprayMlPerTank(parse(dose), parse(tank));
  const tanks = tanksPerAcre(parse(tank));
  return (
    <ToolCard id="spray" icon="💧" title={t("title")} sub={t("sub")}>
      <Field label={t("dose")}>
        {(id) => (
          <input id={id} type="number" inputMode="decimal" min="0" step="0.5" className={inputCls} value={dose} onChange={(e) => setDose(e.target.value)} />
        )}
      </Field>
      <Field label={t("tank")}>
        {(id) => (
          <input id={id} type="number" inputMode="numeric" min="1" className={inputCls} value={tank} onChange={(e) => setTank(e.target.value)} />
        )}
      </Field>
      <Result label={t("resultPerTank")} value={`${num.format(perTank)} ml`} testId="spray-result" />
      {tanks > 0 ? (
        <p className="text-[10.5px] text-muted">
          {t("resultTanks", { tanks: num.format(tanks), volume: SPRAY_VOLUME_L_PER_ACRE })}
        </p>
      ) : null}
    </ToolCard>
  );
}

export function ToolsClient() {
  return (
    <div className="mt-5 grid gap-3 md:grid-cols-2">
      <EmiTool />
      <SeedTool />
      <FertilizerTool />
      <SprayTool />
    </div>
  );
}
