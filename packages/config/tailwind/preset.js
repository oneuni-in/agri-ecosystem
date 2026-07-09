/**
 * @agri/config — Tailwind preset STUB.
 *
 * D02 fills `theme.extend` from docs/design-system.md §1 (tokens: --brand,
 * --brand-deep, --brand-soft, --accent, neutrals, radii, type scale).
 * Until then this exports an intentionally empty theme so the five apps share
 * one preset object from day one and D02 is a single-file change.
 *
 * Per CLAUDE.md: tokens only — no raw hex in app code. Hex values land here.
 *
 * @type {import("tailwindcss").Config}
 */
export const agriPreset = {
  content: [],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default agriPreset;
