import { Eyebrow, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { AskChat } from "./ask-chat";

/**
 * A-U4 W1 — the Ask-AI surface.
 *
 * ONE route serves both states, and that is the point of the build prompt's
 * "build it so the flag flip is the only change needed either way". With
 * `agri_ai` OFF this page renders an honest not-yet state; with it ON the
 * same page renders the chat. There is no second surface to keep in sync and
 * no copy that becomes a lie when the flag moves.
 *
 * The flag is read from the backend (see `assistantEnabled` below), never
 * mirrored into the web app's own config — a second copy of a feature flag
 * is a second thing that can disagree with the first.
 */

const SITE = "https://agri.in";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("ui.agriAsk");
  return buildMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    canonical: canonicalUrl(SITE, "/ask"),
    siteName: "Agri.in",
  });
}

/**
 * Is the assistant switched on?
 *
 * Read from the public `GET /ai/status`, which exists precisely because the
 * obvious approach does not work: probing `/ai/ask` returns 401 whether the
 * flag is on or off, because SecureRouter's auth dependency runs before the
 * flag check. This page shipped that bug briefly and rendered a composer for
 * a disabled assistant — hence a route that answers the actual question.
 *
 * Fails CLOSED. An unreachable or unparseable backend renders the not-yet
 * state, because a composer that cannot send anything is worse than an
 * honest "not on".
 */
async function assistantEnabled(): Promise<boolean> {
  const api = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
  try {
    const res = await fetch(`${api}/ai/status`, { cache: "no-store" });
    if (!res.ok) return false;
    const body = (await res.json()) as { enabled?: boolean };
    return body.enabled === true;
  } catch {
    return false;
  }
}

export default async function AskPage() {
  const [t, enabled] = await Promise.all([getTranslations("ui"), assistantEnabled()]);

  return (
    <main className="bg-cream pb-10">
      <Wrap>
        <nav className="mt-3.5 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted">
          <Link href="/" prefetch={false} className="tap-target text-brand no-underline">
            {t("agriHome.categoriesPage.crumbHome")}
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{t("agriAsk.heading")}</span>
        </nav>

        <div className="mt-2 flex flex-wrap items-start gap-3.5">
          <span
            aria-hidden="true"
            className="flex h-[54px] w-[54px] flex-none items-center justify-center rounded-icon bg-brand-soft text-[26px]"
          >
            🤖
          </span>
          <div className="min-w-0">
            <Eyebrow>{t("agriHome.ask.title")}</Eyebrow>
            <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-semibold leading-[1.15]">
              {t("agriAsk.heading")}
            </h1>
            <p className="mt-[3px] text-[12.5px] text-sub">{t("agriAsk.sub")}</p>
          </div>
        </div>

        {enabled ? (
          <AskChat
            copy={{
              placeholder: t("agriAsk.placeholder"),
              send: t("agriAsk.send"),
              sending: t("agriAsk.sending"),
              sourcesLabel: t("agriAsk.sourcesLabel"),
              disclaimer: t("agriAsk.disclaimer"),
              reviewNote: t("agriAsk.reviewNote"),
              errorTitle: t("agriAsk.errorTitle"),
              routeCta: t("agriAsk.routeCta"),
              emptyState: t("agriAsk.emptyState"),
              loginNeeded: t("agriAsk.loginNeeded"),
            }}
          />
        ) : (
          /* The honest not-yet state. It says what is true — built, not
             switched on, pending a safety review — and sends the visitor to
             the guides the assistant would have answered from, which exist
             today. No email capture, no countdown, no fake queue. */
          <section
            aria-labelledby="ask-soon"
            className="mt-5 rounded-band border border-brand-soft-2 bg-brand-soft p-6"
          >
            <h2
              id="ask-soon"
              className="font-display text-base font-semibold text-brand-deep"
            >
              {t("agriAsk.soonTitle")}
            </h2>
            <p className="mt-1.5 max-w-[60ch] text-[12.5px] leading-[1.6] text-sub">
              {t("agriAsk.soonBody")}
            </p>
            <Link
              href="/knowledge"
              prefetch={false}
              className="tap-target mt-3 inline-flex min-h-[44px] items-center rounded-btn bg-brand px-5 text-[13px] font-bold text-white no-underline"
            >
              {t("agriAsk.soonCta")}
            </Link>
            <p className="mt-3 text-[11px] leading-[1.55] text-muted">
              {t("agriAsk.reviewNote")}
            </p>
            <p className="mt-1 text-[11px] font-medium leading-[1.55] text-sub">
              {t("agriAsk.disclaimer")}
            </p>
          </section>
        )}
      </Wrap>
    </main>
  );
}
