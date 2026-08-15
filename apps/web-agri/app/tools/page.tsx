import { NextIntlClientProvider } from "next-intl";
import { Eyebrow, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { pickUiMessages } from "@/lib/client-messages";
import { ToolsClient } from "./tools-client";

/**
 * A-U1 §10c — `/tools`, the farm-calculators surface the `farm-tools`
 * registry vertical points at. REAL, client-side and offline-capable: all
 * computation lives in @agri/ui's pure `agri-calculators` module (unit
 * tested there), the island below only holds input state — zero fetches,
 * zero server round-trips after load.
 */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("ui.tools");
  return buildMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    canonical: canonicalUrl("https://agri.in", "/tools"),
    siteName: "Agri.in",
  });
}

export default async function ToolsPage() {
  const t = await getTranslations("ui.tools");
  return (
    <main className="bg-cream pb-10">
      <Wrap>
        <nav className="mt-3.5 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted">
          <Link href="/" prefetch={false} className="tap-target text-brand no-underline">
            {t("crumbHome")}
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{t("crumb")}</span>
        </nav>

        <div className="mt-2 flex flex-wrap items-start gap-3.5">
          <span
            aria-hidden="true"
            className="flex h-[54px] w-[54px] flex-none items-center justify-center rounded-icon bg-brand-soft text-[26px]"
          >
            🧮
          </span>
          <div>
            <Eyebrow>{t("eyebrow")}</Eyebrow>
            <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-semibold leading-[1.15]">
              {t("title")}
            </h1>
            <p className="mt-[3px] text-[12.5px] text-sub">{t("sub")}</p>
          </div>
        </div>

        {/* AG-A8: nested provider — this route pays for its own client catalog */}
        <NextIntlClientProvider messages={await pickUiMessages(["tools"])}>
          <ToolsClient />
        </NextIntlClientProvider>

        <p className="mt-5 text-[10.5px] leading-relaxed text-muted">{t("disclaimer")}</p>
      </Wrap>
    </main>
  );
}
