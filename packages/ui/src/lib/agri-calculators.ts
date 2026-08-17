/**
 * A-U1 §10c — farm-calculator maths, pure and offline (`/tools` on
 * web-agri). No I/O, no Date, no locale: components format, this computes.
 * Lives in @agri/ui's lib (web-agri has no vitest harness; this package's
 * test conventions cover it — agri-calculators.test.ts).
 *
 * Every formula is documented at its function; agronomic reference values
 * cite their source in comments. Numbers here are planning aids, not
 * prescriptions — the UI carries that disclaimer.
 */

/** 1 acre = 0.4047 hectare (standard conversion). */
export const HA_PER_ACRE = 0.4047;

export function acresToHectares(acres: number): number {
  return acres * HA_PER_ACRE;
}

/* ── EMI ───────────────────────────────────────────────────────────────── */

/**
 * Standard reducing-balance EMI:
 *   EMI = P·r·(1+r)^n / ((1+r)^n − 1),  r = annualRatePct / 1200
 * r = 0 degenerates to straight division (the formula is 0/0 there).
 * Returns whole rupees (bankers round to the rupee on schedules).
 */
export function emi(principal: number, annualRatePct: number, months: number): number {
  if (principal <= 0 || months <= 0) return 0;
  const r = annualRatePct / 1200;
  if (r === 0) return Math.round(principal / months);
  const factor = Math.pow(1 + r, months);
  return Math.round((principal * r * factor) / (factor - 1));
}

/* ── Seed rate ─────────────────────────────────────────────────────────── */

/**
 * Reference seed rates in kg/ha — agronomic reference values per the TNAU
 * agritech portal (agritech.tnau.ac.in) crop-production guidelines.
 */
export const SEED_RATE_KG_PER_HA = {
  "paddy-transplanted": 30,
  "paddy-direct": 75,
  maize: 20,
  groundnut: 125,
  blackgram: 20,
} as const;

export type SeedCrop = keyof typeof SEED_RATE_KG_PER_HA;

/** Seed needed for `acres` of `crop`, in kg (1 decimal). */
export function seedRequirementKg(crop: SeedCrop, acres: number): number {
  if (acres <= 0) return 0;
  return Math.round(SEED_RATE_KG_PER_HA[crop] * acresToHectares(acres) * 10) / 10;
}

/* ── Fertilizer dose ───────────────────────────────────────────────────── */

/** Recommended NPK doses in kg/ha (N–P₂O₅–K₂O), TNAU crop guides. */
export const NPK_PRESETS_KG_PER_HA = {
  paddy: { n: 120, p: 40, k: 40 },
  maize: { n: 135, p: 62, k: 50 },
} as const;

export type NpkCrop = keyof typeof NPK_PRESETS_KG_PER_HA;

export interface NpkDose {
  /** N, kg/ha. */
  n: number;
  /** P as P₂O₅, kg/ha. */
  p: number;
  /** K as K₂O, kg/ha. */
  k: number;
}

export interface FertilizerPlan {
  /** Urea, kg for the area. */
  urea: number;
  /** DAP, kg for the area (P₂O₅ basis). */
  dap: number;
  /** MOP (muriate of potash), kg for the area. */
  mop: number;
}

/**
 * Simple v1: total nutrient need = recommended dose (kg/ha) × area (ha),
 * converted to product weight by standard nutrient fractions
 * (Fertilizer Control Order product grades):
 *   urea = N / 0.46      (urea is 46% N)
 *   DAP  = P₂O₅ / 0.46   (DAP is 46% P₂O₅; its 18% N is ignored in v1 —
 *                         a deliberate simplification, documented in the UI)
 *   MOP  = K₂O / 0.60    (MOP is 60% K₂O)
 * SHC path: the caller passes soil-test-adjusted doses as `dose`; v1 does
 * not subtract soil values itself. Results in kg, 1 decimal.
 */
export function fertilizerPlan(dose: NpkDose, acres: number): FertilizerPlan {
  if (acres <= 0) return { urea: 0, dap: 0, mop: 0 };
  const ha = acresToHectares(acres);
  const round1 = (x: number) => Math.round(x * 10) / 10;
  return {
    urea: round1((Math.max(0, dose.n) * ha) / 0.46),
    dap: round1((Math.max(0, dose.p) * ha) / 0.46),
    mop: round1((Math.max(0, dose.k) * ha) / 0.6),
  };
}

/* ── Spray dilution ────────────────────────────────────────────────────── */

/** Knapsack spray-volume planning figure: 200 L of spray fluid per acre. */
export const SPRAY_VOLUME_L_PER_ACRE = 200;

/** Chemical per tank: label dose (ml per litre of water) × tank size (L). */
export function sprayMlPerTank(labelDoseMlPerL: number, tankL: number): number {
  if (labelDoseMlPerL <= 0 || tankL <= 0) return 0;
  return Math.round(labelDoseMlPerL * tankL * 10) / 10;
}

/** Tank fills needed per acre at the standard spray volume (1 decimal). */
export function tanksPerAcre(tankL: number, sprayVolumeLPerAcre = SPRAY_VOLUME_L_PER_ACRE): number {
  if (tankL <= 0) return 0;
  return Math.round((sprayVolumeLPerAcre / tankL) * 10) / 10;
}
