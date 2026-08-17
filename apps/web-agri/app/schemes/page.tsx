import { DeadlineItem, DeadlinesBar, Eyebrow, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { pick } from "@/lib/content";
import { fetchSchemes } from "@/lib/schemes";

/**
 * A-U3 W2 — `/schemes`, the "schemes static v0" listing.
 *
 * The entries behind the home spotlight, given their own page. Same
 * backend read as the home, so the two cannot drift.
 *
 * NOT the eligibility wizard. That is Stage C, and the difference
 * matters: this page tells you a scheme exists and links you to the
 * official portal, it does not tell you whether you qualify. Anything
 * that answered "you are eligible" would be advice about money, and
 * that needs a human sign-off this pass does not have.
 */
export const revalidate = 3600;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("ui.schemes");
  return buildMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    canonical: canonicalUrl("https://agri.in", "/schemes"),
    siteName: "Agri.in",
  });
}

export default async function SchemesPage() {
  const [t, locale, block] = await Promise.all([
    getTranslations("ui.schemes"),
    getLocale(),
    fetchSchemes(),
  ]);

  // No verified schemes -> no page. A schemes listing with nothing in it
  // is not a page worth having, and an empty state would imply the
  // dataset is coming rather than absent.
  if (block.items.length === 0) notFound();

  return (
    <main className="bg-cream pb-10">
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
          {t("title")}
        </h1>
        <p className="mt-1 max-w-[70ch] text-[13px] text-muted">{t("sub")}</p>

        {/* Deadlines the service has already filtered: a `due_on` that has
            passed is dropped upstream, so this bar can never advertise a
            window that closed. */}
        {block.deadlines.length > 0 ? (
          <div className="mt-4">
            <DeadlinesBar heading={t("deadlinesTitle")}>
              {block.deadlines.map((deadline) => (
                <DeadlineItem
                  key={deadline.chip + pick(locale, deadline.title)}
                  chip={deadline.chip}
                >
                  {pick(locale, deadline.title)}
                  {deadline.note ? (
                    <span className="text-muted">
                      {" "}
                      · {pick(locale, deadline.note)}
                    </span>
                  ) : null}
                </DeadlineItem>
              ))}
            </DeadlinesBar>
          </div>
        ) : null}

        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {block.items.map((scheme) => (
            <article
              key={scheme.url}
              className="flex flex-col rounded-card border border-cream-line bg-card p-4"
            >
              <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                <span className="rounded-pill bg-brand-soft px-2 py-0.5 text-[10px] font-semibold text-brand-deep">
                  {t(`levels.${scheme.level}`)}
                </span>
                {scheme.state_label ? (
                  <span className="rounded-pill bg-accent-soft px-2 py-0.5 text-[10px] font-semibold text-coins-fg">
                    {pick(locale, scheme.state_label)}
                  </span>
                ) : null}
              </div>
              <h2 className="text-[15.5px] font-extrabold leading-[1.3] text-ink">
                {pick(locale, scheme.title)}
              </h2>
              <p className="mt-1 flex-1 text-[13px] leading-[1.55] text-muted">
                {pick(locale, scheme.body)}
              </p>

              {/* The stamp, from the row. Not decoration: it is how a
                  reader can tell a current card from a stale one. */}
              <p className="mt-2.5 text-[10.5px] text-muted">
                {t("verifiedStamp", {
                  domain: scheme.verified_against,
                  date: scheme.verified_on,
                })}
              </p>

              <a
                href={scheme.url}
                target="_blank"
                rel="noopener"
                className="mt-2.5 inline-flex min-h-[44px] items-center justify-center rounded-btn bg-brand px-4 text-[13px] font-semibold text-white no-underline"
              >
                {pick(locale, scheme.link_label)}
              </a>
            </article>
          ))}
        </div>

        {/* Stage C is the wizard. Saying so is better than a reader
            assuming this page already answered the eligibility question. */}
        <p className="mt-6 rounded-card border border-cream-line bg-card p-4 text-[12.5px] text-muted">
          {t("eligibilityNote")}
        </p>
      </Wrap>
    </main>
  );
}
