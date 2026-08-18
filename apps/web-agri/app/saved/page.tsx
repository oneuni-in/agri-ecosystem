import { KnowledgeCard, Wrap, Eyebrow } from "@agri/ui";
import type { Metadata } from "next";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";
import { formatDuration, pick, type ContentCard } from "@/lib/content";

/**
 * A-U4 W4 — saved items.
 *
 * Two jobs. It is the surface for a bookmark feature that has had a button
 * since A-U3 and nowhere to see the result, and it is one of the three routes
 * the service worker keeps offline — saving something to read later is close
 * to a declaration that you expect to read it somewhere without signal.
 *
 * `noindex` and auth-gated: this is one person's list.
 *
 * Rendered SERVER-side rather than as a client island, deliberately: the
 * service worker caches the rendered document, so what a visitor gets offline
 * is their actual list. An island would cache a shell that then failed to
 * fetch, which is a worse offline experience than no page at all.
 */
export const metadata: Metadata = { title: "Saved", robots: { index: false } };

export const dynamic = "force-dynamic";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

async function fetchSaved(token: string): Promise<ContentCard[]> {
  try {
    const res = await fetch(`${API}/content/bookmarks?limit=50`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return [];
    const body = (await res.json()) as { items?: ContentCard[] };
    return body.items ?? [];
  } catch {
    return [];
  }
}

export default async function SavedPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/saved");

  const token = await auth.getAccessToken();
  const [t, locale, items] = await Promise.all([
    getTranslations("ui"),
    getLocale(),
    token ? fetchSaved(token) : Promise.resolve([]),
  ]);

  return (
    <main className="bg-cream pb-10">
      <Wrap>
        <div className="mt-4">
          <Eyebrow>{t("saved.eyebrow")}</Eyebrow>
          <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-semibold leading-[1.15]">
            {t("saved.title")}
          </h1>
        </div>

        {items.length === 0 ? (
          <div className="mt-5 rounded-card border border-cream-line bg-card px-5 py-8 text-center">
            <p className="text-[13px] text-sub">{t("saved.empty")}</p>
            <Link
              href="/knowledge"
              prefetch={false}
              className="tap-target mt-3 inline-flex min-h-[44px] items-center rounded-btn bg-brand px-5 text-[13px] font-bold text-white no-underline"
            >
              {t("saved.browse")}
            </Link>
          </div>
        ) : (
          <div className="mt-5 grid gap-2.5 max-md:grid-cols-1 md:grid-cols-3">
            {items.map((item) => (
              <KnowledgeCard
                key={item.id}
                href={`/knowledge/${item.slug}`}
                icon={item.kind === "video" ? "🎬" : "🌾"}
                isVideo={item.kind === "video"}
                titleAs="h2"
                duration={formatDuration(item.duration_seconds)}
                category={t(`knowledge.kinds.${item.kind}`)}
                title={pick(locale, item.title)}
                meta={item.source_name}
              />
            ))}
          </div>
        )}

        {/* Says plainly that this page works offline — the reason it is one
            of the three routes the worker keeps. */}
        <p className="mt-5 text-[11px] text-muted">{t("saved.offlineNote")}</p>
      </Wrap>
    </main>
  );
}
