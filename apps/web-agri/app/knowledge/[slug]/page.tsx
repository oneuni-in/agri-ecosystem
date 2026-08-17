import { Eyebrow, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { BookmarkButton } from "@/app/knowledge/bookmark-button";
import { fetchContentItem, formatDuration, pick } from "@/lib/content";

/**
 * A-U3 W1 — one content item.
 *
 * A pending, rejected or nonexistent slug all 404 identically, because
 * the backend returns null for all three. A slug guess therefore reveals
 * nothing about what is sitting in the moderation queue.
 *
 * Attribution is the page's spine, not a footnote: the source name, the
 * publisher's date and the link back to the original are rendered from
 * the row, above the fold. For a feed item there is no body to show —
 * we link out rather than restate someone else's article, so the primary
 * action on this page is "read it at the source".
 */
export const revalidate = 300;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const item = await fetchContentItem(slug);
  if (!item) {
    return buildMetadata({
      title: "Knowledge · agri.in",
      canonical: canonicalUrl("https://agri.in", `/knowledge/${slug}`),
      noIndex: true,
    });
  }
  const description = item.summary["en"];
  return buildMetadata({
    title: `${item.title["en"] ?? slug} · agri.in`,
    ...(description ? { description } : {}),
    canonical: canonicalUrl("https://agri.in", `/knowledge/${slug}`),
    siteName: "Agri.in",
  });
}

export default async function ContentItemPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const [{ slug }, t, locale] = await Promise.all([
    params,
    getTranslations("ui.knowledge"),
    getLocale(),
  ]);
  const item = await fetchContentItem(slug);
  if (!item) notFound();

  const duration = formatDuration(item.duration_seconds);
  const published = new Date(item.published_at).toLocaleDateString(locale, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

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
          <Link
            href="/knowledge"
            prefetch={false}
            className="tap-target text-brand no-underline"
          >
            {t("crumb")}
          </Link>
        </nav>

        <article className="mt-3 max-w-[74ch]">
          <Eyebrow>{t(`kinds.${item.kind}`)}</Eyebrow>
          <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-extrabold leading-[1.25] text-ink">
            {pick(locale, item.title)}
          </h1>

          {/* Attribution, from the row. Every field here is NOT NULL on
              the wire, so this block can never render half-empty. */}
          <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px] text-muted">
            <a
              href={item.source_url}
              rel="noopener nofollow"
              className="font-semibold text-brand-deep no-underline"
            >
              {item.source_name}
            </a>
            <span aria-hidden="true">·</span>
            <time dateTime={item.published_at}>{published}</time>
            {duration ? (
              <>
                <span aria-hidden="true">·</span>
                <span>{t("durationLabel", { duration })}</span>
              </>
            ) : null}
            <span aria-hidden="true">·</span>
            <span>{t(`languages.${item.language}`)}</span>
          </p>

          <div className="mt-3">
            <BookmarkButton
              itemId={item.id}
              initiallySaved={item.bookmarked}
              saveLabel={t("save")}
              savedLabel={t("saved")}
            />
          </div>

          {/* Approved-provider embed only. embed_url is BUILT server-side
              from the allowlist — this page never receives markup or an
              arbitrary origin, so there is no iframe HTML to sanitise. */}
          {item.embed_url ? (
            <div className="mt-4 aspect-video overflow-hidden rounded-card border border-cream-line bg-ink">
              <iframe
                src={item.embed_url}
                title={pick(locale, item.title)}
                loading="lazy"
                allowFullScreen
                referrerPolicy="strict-origin-when-cross-origin"
                allow="accelerometer; encrypted-media; gyroscope; picture-in-picture"
                className="h-full w-full border-0"
              />
            </div>
          ) : null}

          <p className="mt-4 text-[14.5px] leading-[1.6] text-ink">
            {pick(locale, item.summary)}
          </p>

          {item.body ? (
            <div className="mt-4 whitespace-pre-line text-[14.5px] leading-[1.7] text-ink">
              {pick(locale, item.body)}
            </div>
          ) : null}

          {/* Feed items have no body here BY DESIGN — the article belongs
              to its publisher and this is the door to it. */}
          {item.canonical_url ? (
            <a
              href={item.canonical_url}
              rel="noopener nofollow"
              className="mt-5 inline-flex min-h-[44px] items-center rounded-btn bg-brand px-5 text-sm font-semibold text-white no-underline"
            >
              {t("readAtSource", { source: item.source_name })}
            </a>
          ) : null}
        </article>
      </Wrap>
    </main>
  );
}
