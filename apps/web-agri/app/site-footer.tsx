import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { fetchVerticals } from "@/lib/home";

/**
 * A-U1 §22 — the agri.in footer per A1 FINAL v4: brand blurb with the
 * neutrality line, then Categories / States / For business / Company
 * columns, then the legal row.
 *
 * Link honesty rule (build prompt "no dead links anywhere"): only routes
 * that resolve TODAY are anchors — the Business Console (`/business`,
 * `/business/ads`) and `/notifications`. Everything else renders as the
 * plain-text `<li>` entries A1's own footer uses (its column items carry no
 * hrefs); they become links as their surfaces land (CP3 `/categories`,
 * later state pages).
 */
export async function SiteFooter() {
  // The category count is REGISTRY DATA, not a literal: A-U2 added three
  // Soon verticals by migration alone, and a hardcoded "36" in this
  // column would have quietly started lying the moment it landed. Next
  // dedupes this against the home's identical registry read.
  const [t, verticals] = await Promise.all([
    getTranslations("ui.agriHome.footer"),
    fetchVerticals(),
  ]);
  return (
    <footer className="mt-6 bg-brand-deep text-brand-soft-2">
      <div className="mx-auto max-w-[1140px] px-4">
        <div className="grid grid-cols-2 gap-5 py-6 md:grid-cols-[1.3fr_1fr_1fr_1fr_1fr]">
          <div className="col-span-2 md:col-span-1">
            <b className="font-display text-[17px] font-extrabold text-white">agri.in</b>
            <p className="mt-1.5 text-[11px] leading-relaxed">{t("about")}</p>
            <p className="mt-1.5 text-[11px] font-semibold leading-relaxed text-white">
              {t("neutrality")}
            </p>
          </div>

          <FooterCol title={t("categories")}>
            <li>{t("catMandi")}</li>
            <li>{t("catWeather")}</li>
            <li>{t("catSchemes")}</li>
            <li>{t("catAll", { count: verticals.length })}</li>
          </FooterCol>

          <FooterCol title={t("states")}>
            <li>{t("stTn")}</li>
            <li>{t("stKa")}</li>
            <li>{t("stApTg")}</li>
            <li>{t("stAll")}</li>
          </FooterCol>

          <FooterCol title={t("forBusiness")}>
            <FooterLink href="/business">{t("listFree")}</FooterLink>
            <FooterLink href="/business/ads">{t("advertise")}</FooterLink>
            <FooterLink href="/business">{t("console")}</FooterLink>
            <li>{t("verification")}</li>
          </FooterCol>

          <FooterCol title={t("company")}>
            <li>{t("aboutUs")}</li>
            <FooterLink href="/notifications">{t("contact")}</FooterLink>
            <li>{t("privacy")}</li>
            <li>{t("terms")}</li>
          </FooterCol>
        </div>

        <div className="flex flex-col gap-1 border-t border-white/20 py-3 text-[10.5px] md:flex-row md:items-center md:gap-4">
          <span>{t("legal", { year: 2026 })}</span>
          <span className="text-brand-soft md:ml-auto">{t("languages")}</span>
        </div>
      </div>
    </footer>
  );
}

function FooterCol({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-[12px] font-semibold text-white">{title}</h3>
      <ul className="list-none text-[11px] leading-[2.1]">{children}</ul>
    </div>
  );
}

function FooterLink({ href, children }: { href: string; children: ReactNode }) {
  // `.tap-target` (§1.5) + the WCAG 2.2 24px row floor, exactly as milk's
  // footer documents the pairing.
  return (
    <li>
      <a
        href={href}
        className="tap-target inline-flex min-h-[24px] items-center no-underline hover:text-white"
      >
        {children}
      </a>
    </li>
  );
}
