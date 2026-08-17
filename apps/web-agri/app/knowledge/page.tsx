import { Eyebrow, KnowledgeCard, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import {
  fetchFeed,
  formatDuration,
  pick,
  type ContentCard,
  type ContentKind,
} from "@/lib/content";

/**
 * A-U3 W1 — `/knowledge`, the content hub.
 *
 * The honesty rule decides whether this page exists at all. The backend
 * serves APPROVED items only, so an empty feed means the module is empty
 * or nothing has cleared the human gate — and in both cases the page
 * 404s rather than rendering a heading over nothing. There is no "no
 * articles yet" empty state, because an empty content hub is not a
 * surface worth having.
 *
 * Filtering is a LINK, not an island: `?kind=video` re-renders on the
 * server. The tabs work without JS, they are crawlable, and the page
 * ships no client bundle for something a query string already does.
 */
export const dynamic = "force-dynamic";

const KINDS: readonly ContentKind[] = [
  "article",
  "video",
  "guide",
  "advisory",
] as const;

function parseKind(raw: string | undefined): ContentKind | undefined {
  return KINDS.find((k) => k === raw);
}

export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<{ kind?: string }>;
}): Promise<Metadata> {
  const t = await getTranslations("ui.knowledge");
  const kind = parseKind((await searchParams).kind);
  return buildMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    // A filtered view is the same content re-sliced, so it points its
    // canonical at the unfiltered hub rather than competing with it.
    canonical: canonicalUrl("https://agri.in", "/knowledge"),
    siteName: "Agri.in",
    noIndex: Boolean(kind),
  });
}

/** The kind pill on a card. Video leads with the play glyph, matching A1. */
function categoryLabel(item: ContentCard, label: string): string {
  return item.kind === "video" ? `▶ ${label}` : label;
}

/** Emoji stand-in per kind — artwork is Stage C; these are not data. */
const KIND_ICON: Record<ContentKind, string> = {
  article: "📰",
  video: "🎬",
  guide: "🌾",
  advisory: "🐛",
};

export default async function KnowledgePage({
  searchParams,
}: {
  searchParams: Promise<{ kind?: string }>;
}) {
  const [t, locale, params] = await Promise.all([
    getTranslations("ui.knowledge"),
    getLocale(),
    searchParams,
  ]);
  const kind = parseKind(params.kind);
  // Conditional spread, not `kind: undefined` — exactOptionalPropertyTypes
  // treats an explicit undefined as a different thing from an absent key.
  const page = await fetchFeed({ ...(kind ? { kind } : {}), limit: 24 });

  // Nothing approved -> no page. Never a heading over an empty grid.
  if (page.items.length === 0 && !kind) notFound();

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

        {/* Server-rendered filter links — no island, no JS needed. */}
        <div
          className="mt-4 flex flex-wrap gap-2"
          role="navigation"
          aria-label={t("filterLabel")}
        >
          <Link
            href="/knowledge"
            prefetch={false}
            aria-current={kind ? undefined : "page"}
            className={`tap-target inline-flex items-center rounded-pill border px-3.5 text-[12.5px] font-semibold no-underline ${
              kind
                ? "border-cream-line bg-card text-ink"
                : "border-brand bg-brand text-white"
            }`}
          >
            {t("all")}
          </Link>
          {KINDS.map((k) => (
            <Link
              key={k}
              href={`/knowledge?kind=${k}`}
              prefetch={false}
              aria-current={kind === k ? "page" : undefined}
              className={`tap-target inline-flex items-center rounded-pill border px-3.5 text-[12.5px] font-semibold no-underline ${
                kind === k
                  ? "border-brand bg-brand text-white"
                  : "border-cream-line bg-card text-ink"
              }`}
            >
              {t(`kinds.${k}`)}
            </Link>
          ))}
        </div>

        {page.items.length === 0 ? (
          // Reachable only for a FILTERED view: the unfiltered empty case
          // already 404'd. Here the heading is warranted — the reader
          // asked a question ("show me videos") and deserves the answer.
          <p className="mt-6 rounded-card border border-cream-line bg-card p-5 text-[13px] text-muted">
            {t("noneOfKind")}
          </p>
        ) : (
          <div className="mt-5 grid gap-2.5 max-md:grid-cols-1 md:grid-cols-3 lg:grid-cols-4">
            {page.items.map((item) => (
              <KnowledgeCard
                key={item.id}
                href={`/knowledge/${item.slug}`}
                icon={KIND_ICON[item.kind]}
                isVideo={item.kind === "video"}
                // Directly under the page h1, so the card titles are h2.
                // Without this the document jumped h1 -> the footer's h3
                // and axe flagged heading-order (a11y 0.94 in CI).
                titleAs="h2"
                duration={formatDuration(item.duration_seconds)}
                category={categoryLabel(item, t(`kinds.${item.kind}`))}
                title={pick(locale, item.title)}
                // Attribution on every card, from data, never a literal.
                meta={`${item.source_name} · ${new Date(
                  item.published_at,
                ).toLocaleDateString(locale, {
                  day: "numeric",
                  month: "short",
                })}`}
              />
            ))}
          </div>
        )}
      </Wrap>
    </main>
  );
}
