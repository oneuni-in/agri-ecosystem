/**
 * Config-driven contact/commercial surfaces for the utility strip (U1 §1).
 *
 * Copy that changes with the business — the hotline number, the advertise
 * door — is configuration, never a literal in a component. U1's binding
 * rules allow exactly two kinds of static content on this page: i18n content
 * components and config-driven strings; these are the latter.
 *
 * `NEXT_PUBLIC_*` is inlined at build time (the Next.js convention), so an
 * unset value is unrecoverable at runtime. That is deliberate for the
 * hotline: unset simply means "no hotline yet", and §1 requires the slot to
 * render with the chip absent rather than showing an empty golden box.
 */
export const WHATSAPP_HOTLINE: string = process.env.NEXT_PUBLIC_WHATSAPP_HOTLINE ?? "";

/** `wa.me` wants bare digits — strip spaces, dashes and the leading `+`. */
export function hotlineHref(number: string): string {
  return `https://wa.me/${number.replace(/\D/g, "")}`;
}

/** The M5 advertiser self-serve wizard, in the Business Console. A door to
 * an existing flow — no new route on milk.in. */
export function advertiseHref(base: string): string {
  return `${base.replace(/\/+$/, "")}/business/ads`;
}
