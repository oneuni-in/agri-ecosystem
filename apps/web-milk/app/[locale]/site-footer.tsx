import { LowDataToggle } from "@agri/ui";
import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import { CATEGORY_MESSAGE_KEY, DAIRY_CATEGORIES } from "@/lib/categories";
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
  const [t, tCat, tAdv, tLowData, categories] = await Promise.all([
    getTranslations("ui.home.footer"),
    getTranslations("ui.dairyCategories"),
    getTranslations("ui.home.advertise"),
    getTranslations("ui.lowData"),
    fetchProductCategories(locale),
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
            {DAIRY_CATEGORIES.slice(0, 3).map((slug) => (
              <FooterLink key={slug} href={`/c/${slug}`}>
                {tCat(`${CATEGORY_MESSAGE_KEY[slug]}.name`)}
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
      <ul className="list-none text-[11px] leading-[2.1]">{children}</ul>
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
  return (
    <li>
      {external ? (
        <a href={href} className="no-underline hover:text-white">
          {children}
        </a>
      ) : (
        <Link href={href} prefetch={false} className="no-underline hover:text-white">
          {children}
        </Link>
      )}
    </li>
  );
}
