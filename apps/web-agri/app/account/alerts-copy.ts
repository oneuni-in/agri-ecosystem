import type { AlertsCopy } from "./alerts-manager";

/**
 * The alerts island's strings, resolved on the server and handed down.
 *
 * Two surfaces render the same list — the overview panel and
 * /account/alerts — and both are Server Components, so the copy is built
 * once here rather than by mounting a second NextIntlClientProvider around a
 * five-string component (AG-A8 payload discipline: the root provider carries
 * public-page namespaces only, and `ui.account` is not one of them).
 */
/** next-intl's translator: callable, plus `.raw` for an unformatted message. */
type Translator = ((key: string) => string) & { raw: (key: string) => unknown };

export function alertsCopy(t: Translator): AlertsCopy {
  return {
    digest: t("panels.alertsDigest"),
    what: t("panels.alertsWhat"),
    // `.raw`, not `t()`: this message carries a {date} placeholder and the
    // value is per-row, so it travels to the island with the placeholder
    // intact. Calling t() here would demand a date we do not have yet.
    lastSent: String(t.raw("panels.alertsLastSent")),
    never: t("panels.alertsNever"),
    off: t("panels.alertsOff"),
    offBusy: t("panels.alertsOffBusy"),
    offFailed: t("panels.alertsOffFailed"),
    empty: t("panels.alertsEmpty"),
  };
}
