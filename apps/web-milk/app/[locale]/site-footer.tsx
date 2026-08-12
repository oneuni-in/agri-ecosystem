import { LowDataToggle } from "@agri/ui";
import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import { categoryLabel, fetchBusinessCategories } from "@/lib/categories";
import { CONSOLE_URL, listingsHref } from "@/lib/console";
import { advertiseHref, advertisePrice } from "@/lib/contact";
import { fetchProductCategories } from "@/lib/taxonomy";

/**
 * §11 — the site footer: 5 columns on desktop, stacked on mobile, with the
 * neutrality line rendered verbatim.
 *
 * Categories and services are read from the same D17 sources the rest of the
 * page uses (never a hardcoded list), and the ₹ line is the shared
 * shared advertise-price config, so the CTA tile and the footer can never disagree.
 * Data-saver stays here, below the fold, for the reason the old footer
 * documented: the header's right cluster already hydrates three islands and a
 * fourth measurably cost CLS on the Lighthouse-audited home.
 */
export async function SiteFooter({ locale }: { locale: string }) {
  const [t, tAdv, tLowData, categories, businessCategories] = await Promise.all([
    getTranslations("ui.home.footer"),
    getTranslations("ui.home.advertise"),
    getTranslations("ui.lowData"),
    fetchProductCategories(locale),
    fetchBusinessCategories(),
  ]);

  return (
    <footer className="mt-6 bg-brand-deep text-brand-soft-2">
      <div className="mx-auto max-w-[1140px] px-4">
        <div className="grid grid-cols-2 gap-5 py-6 md:grid-cols-[1.3fr_1fr_1fr_1fr_1fr]">
          <div className="col-span-2 md:col-span-1">
            <b className="font-display text-[17px] font-extrabold text-white">milk.in</b>
            <p className="mt-1.5 text-[11px] leading-relaxed">{t("about")}</p>
            <p className="mt-1.5 text-[11px] font-semibold leading-relaxed text-white">
              {t("neutrality")}
            </p>
          </div>

          <FooterCol title={t("categories")}>
            {categories.slice(0, 3).map((category) => (
              <FooterLink key={category.value} href={`/p/${category.value}`}>
                {category.label}
              </FooterLink>
            ))}
            <FooterLink href="/search">{t("allCategories")}</FooterLink>
          </FooterCol>

          <FooterCol title={t("forVendors")}>
            <FooterLink href={listingsHref(CONSOLE_URL)} external>
              {t("listFree")}
            </FooterLink>
            <FooterLink href={advertiseHref(CONSOLE_URL)} external>
              {t("advertise")} · {advertisePrice(tAdv("perWeek"))}
            </FooterLink>
            <FooterLink href={CONSOLE_URL} external>
              {t("console")}
            </FooterLink>
          </FooterCol>

          <FooterCol title={t("cities")}>
            {/* U1b: the /c links are the public taxonomy read, never a list
                in code — same source as the chips and the §8g tiles. */}
            {businessCategories.slice(0, 3).map((category) => (
              <FooterLink key={category.slug} href={`/c/${category.slug}`}>
                {categoryLabel(category, locale)}
              </FooterLink>
            ))}
            <FooterLink href="/search">{t("allCities")}</FooterLink>
          </FooterCol>

          <FooterCol title={t("company")}>
            <FooterLink href="/notifications">{t("aboutUs")}</FooterLink>
            <FooterLink href="/post-need">{t("contact")}</FooterLink>
            <FooterLink href="/offline">{t("privacy")}</FooterLink>
            <FooterLink href="/offline">{t("terms")}</FooterLink>
          </FooterCol>
        </div>

        <div className="flex flex-col gap-1 border-t border-white/20 py-3 text-[10.5px] md:flex-row md:items-center md:gap-4">
          <span>{t("legal", { year: 2026 })}</span>
          <span className="md:ml-auto">
            <LowDataToggle
              label={tLowData("label")}
              onLabel={tLowData("on")}
              offLabel={tLowData("off")}
              // The toggle defaults to --sub, a light-background colour that
              // measures 1.55:1 on this dark footer.
              className="text-brand-soft-2"
            />
          </span>
        </div>
      </div>
    </footer>
  );
}

function FooterCol({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-[12px] font-semibold text-white">{title}</h3>
      <ul className="list-none text-[11px]">{children}</ul>
    </div>
  );
}

function FooterLink({
  href,
  external = false,
  children,
}: {
  href: string;
  external?: boolean;
  children: React.ReactNode;
}) {
  // Two floors meet here. `min-h-[24px]` clears WCAG 2.2's target-size
  // minimum (axe flagged the bare ~23px text rows), and `.tap-target` — the
  // design system's own §1.5 mechanism, an ::after overlay sized
  // max(100%, 44px) — carries the 44px thumb floor the D29 device matrix
  // enforces, without changing the footer's compact row spacing.
  const className = "tap-target inline-flex min-h-[24px] items-center no-underline hover:text-white";
  return (
    <li>
      {external ? (
        <a href={href} className={className}>
          {children}
        </a>
      ) : (
        <Link href={href} prefetch={false} className={className}>
          {children}
        </Link>
      )}
    </li>
  );
}
