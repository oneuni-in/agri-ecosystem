import { Wrap } from "@agri/ui";
import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

/**
 * A-U4 W4 — the offline shell.
 *
 * Served by the service worker for any navigation that fails with no cached
 * copy of that page. Its whole job is to be USEFUL rather than apologetic:
 * it names the pages that ARE available offline and links to them, because a
 * farmer with no signal needs the helpline number, not an explanation of what
 * a network is.
 *
 * `noindex`: a crawler seeing this would index an error state as content.
 *
 * Copy lives under `ui.agriOffline`, NOT `ui.offline`. That namespace is
 * milk.in's — its own offline shell has used it since D28 — and this page
 * originally overwrote it, deleting five of milk's keys and breaking its
 * build. The i18n catalogue is SHARED across every app in the family, so a
 * new block needs a new name, not a familiar one.
 *
 * Deliberately STATIC — no data reads, no islands. A page that only ever
 * renders when the network is gone cannot depend on the network to render.
 */
export const metadata: Metadata = { title: "Offline", robots: { index: false } };

export default async function OfflinePage() {
  const t = await getTranslations("ui.agriOffline");
  return (
    <main className="bg-cream pb-10">
      <Wrap>
        <section className="mt-8 rounded-band border border-cream-line bg-card px-6 py-8 text-center">
          <span aria-hidden="true" className="text-[40px]">
            📡
          </span>
          <h1 className="mt-2 font-display text-[22px] font-semibold text-ink">
            {t("title")}
          </h1>
          <p className="mx-auto mt-1.5 max-w-[46ch] text-[13px] leading-[1.6] text-sub">
            {t("body")}
          </p>

          <h2 className="mt-6 text-[12px] font-semibold uppercase tracking-wide text-muted">
            {t("availableTitle")}
          </h2>
          <ul className="mx-auto mt-2 flex max-w-[420px] list-none flex-col gap-2 p-0">
            {[
              { href: "/helplines", key: "helplines", icon: "📞" },
              { href: "/mandi", key: "mandi", icon: "🌾" },
              { href: "/saved", key: "saved", icon: "🔖" },
            ].map((entry) => (
              <li key={entry.key}>
                <Link
                  href={entry.href}
                  prefetch={false}
                  className="flex min-h-[44px] items-center gap-2.5 rounded-btn border border-cream-line bg-cream px-4 text-[13px] font-medium text-ink no-underline"
                >
                  <span aria-hidden="true">{entry.icon}</span>
                  {t(`links.${entry.key}`)}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </Wrap>
    </main>
  );
}
