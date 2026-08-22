import type { Tint } from "@agri/ui";

/**
 * A-U6 — the product media band's pastel palette.
 *
 * Deliberately a SERVER-safe module, separate from `product-thumb.tsx`: that
 * file is a client component (it needs an `onError` handler), and a function
 * exported from a "use client" module cannot be CALLED on the server, only
 * rendered. Server pages pick the tint while building the list, so the picker
 * lives here.
 *
 * The tint is decorative chrome — it carries no meaning and nothing reads it
 * back — so it is chosen by position, not derived from product data.
 */

/** The A2 reference's `.pcard .media` palette, in its order. */
export const THUMB_TINTS: Tint[] = ["leaf", "cream", "blush", "green", "sky", "sand"];

export function tintFor(index: number): Tint {
  return THUMB_TINTS[index % THUMB_TINTS.length] as Tint;
}
