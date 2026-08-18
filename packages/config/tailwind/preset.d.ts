import type { Config } from "tailwindcss";

/** Design tokens from docs/design-system.md §1 (D02). */
export declare const agriPreset: Config;
export default agriPreset;

/** Literal token values for surfaces that cannot use CSS vars (PWA manifest). */
export declare const manifestColors: { background: string; theme: string };
