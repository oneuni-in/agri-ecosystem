import { Eyebrow, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { pick } from "@/lib/content";
import { fetchHelplines } from "@/lib/helplines";

import { RegisterHelplineSW } from "./register-sw";

/**
 * A-U3 W2 — the offline click-to-call page.
 *
 * The one page on agri.in that has to work when nothing else does. A
 * farmer who needs the Kisan Call Centre number is often exactly the
 * farmer with no signal, so this page is built to be cacheable and to
 * survive being served from that cache:
 *
 *  - STATICALLY rendered (no `force-dynamic`, no cookies, no per-visitor
 *    branch), so the service worker can hold one copy that is correct
 *    for everyone.
 *  - Numbers come from E5 at build/revalidate time and are baked into
 *    the HTML. Nothing here fetches at runtime, so an offline load
 *    renders exactly what an online load renders.
 *  - `tel:` links need no network at all — tapping one hands off to the
 *    dialer, which is the whole point.
 *
 * National numbers only. State scoping needs the visitor's location,
 * which would make the page per-visitor and therefore uncacheable — and
 * an offline page that only works for people whose location we already
 * knew is not an offline page.
 */
export const revalidate = 86_400;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("ui.helplinesPage");
  return buildMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    canonical: canonicalUrl("https://agri.in", "/helplines"),
    siteName: "Agri.in",
  });
}

export default async function HelplinesPage() {
  const [t, locale, helplines] = await Promise.all([
    getTranslations("ui.helplinesPage"),
    getLocale(),
    fetchHelplines(),
  ]);

  // A helpline page with no numbers is worse than no page: it looks like
  // an answer and is not one.
  if (helplines.length === 0) notFound();

  return (
    <main className="bg-cream pb-10">
      {/* Opting THIS page into offline caching. Mounted here and nowhere
          else — see register-sw.tsx for why that placement is the scope
          boundary against A-U4's PWA work. */}
      <RegisterHelplineSW />
      <Wrap>
        <nav className="mt-3.5 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted">
          <Link
            href="/"
            prefetch={false}
            className="tap-target text-brand no-underline"
          >
            {t("crumbHome")}
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{t("crumb")}</span>
        </nav>

        <Eyebrow className="mt-3">{t("eyebrow")}</Eyebrow>
        <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-extrabold text-ink">
          📞 {t("title")}
        </h1>
        <p className="mt-1 max-w-[70ch] text-[13px] text-muted">{t("sub")}</p>

        {/* Big tap targets, one per number. Sized well past the 44px floor
            on purpose — this page gets used one-handed, outdoors, in a
            hurry. */}
        <ul className="mt-5 grid list-none gap-2.5 p-0 md:grid-cols-2">
          {helplines.map((helpline) => (
            <li key={helpline.slug}>
              <a
                href={`tel:${helpline.dial}`}
                className="flex min-h-[72px] flex-col justify-center rounded-card border border-cream-line bg-card px-4 py-3 no-underline hover:border-brand"
              >
                <b className="text-[15px] font-extrabold text-brand-deep">
                  {pick(locale, helpline.name)}
                </b>
                <span className="font-display text-xl font-extrabold tracking-wide text-ink">
                  {helpline.number}
                </span>
                {/* Per-number provenance — the reason this moved to E5. */}
                <small className="mt-0.5 text-[10.5px] text-muted">
                  {t("verifiedStamp", {
                    domain: helpline.source,
                    date: helpline.verified_on,
                  })}
                </small>
              </a>
            </li>
          ))}
        </ul>

        <p className="mt-5 rounded-card border border-cream-line bg-card p-4 text-[12.5px] text-muted">
          {t("offlineNote")}
        </p>
      </Wrap>
    </main>
  );
}
