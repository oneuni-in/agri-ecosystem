import { CertBar, CertCard, EcoPill, EcoStrip, Section } from "@agri/ui";
import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import { CONSOLE_URL, listingsHref } from "@/lib/console";
import { ORGANIC_URL, advertiseHref, advertisePrice } from "@/lib/contact";

/** §6 — static i18n content component (explicitly allowed by U1). */
export async function TrustRow() {
  const t = await getTranslations("ui.home.trust");
  return (
    <Section title={t("title")}>
      <CertBar>
        <CertCard icon="🇮🇳" title={t("npop.name")} sub={t("npop.sub")} />
        <CertCard icon="🤝" title={t("pgs.name")} sub={t("pgs.sub")} />
        <CertCard icon="🌎" title={t("usda.name")} sub={t("usda.sub")} />
        <CertCard gold icon="✔️" title={t("verify.name")} sub={t("verify.sub")} />
      </CertBar>
    </Section>
  );
}

/**
 * §9 — the two big CTA tiles. Both are doors into EXISTING flows: post-need
 * is the D25 route, "List my business" is the D16 claim/create flow in the
 * Business Console. The ₹ amount is config and the "/week" suffix is translated, so changing the
 * rate card updates this tile and the footer together with no code change.
 */
export async function HomeCtaTiles({ pincode }: { pincode: string }) {
  const [t, tAdv] = await Promise.all([
    getTranslations("ui.home.cta"),
    getTranslations("ui.home.advertise"),
  ]);
  return (
    <div className="mt-5 grid gap-3 md:grid-cols-2">
      <div className="rounded-card bg-brand p-5 text-white">
        <span aria-hidden="true" className="text-[22px]">
          🎙️
        </span>
        <b className="mt-1.5 block font-display text-[17px] font-extrabold">{t("needTitle")}</b>
        <p className="mb-3 text-[12px] text-brand-soft">{t("needSub", { pincode })}</p>
        <Link
          href="/post-need"
          prefetch={false}
          data-testid="home-post-need-cta"
          className="inline-flex min-h-[44px] items-center rounded-btn bg-cream px-4 text-[14px] font-bold text-brand-deep no-underline"
        >
          {t("needCta")}
        </Link>
      </div>
      <div className="rounded-card bg-brand-deep p-5 text-white">
        <span aria-hidden="true" className="text-[22px]">
          🏪
        </span>
        <b className="mt-1.5 block font-display text-[17px] font-extrabold">{t("listTitle")}</b>
        <p className="mb-3 text-[12px] text-brand-soft-2">
          {t("listSub", { price: advertisePrice(tAdv("perWeek")) })}
        </p>
        <span className="flex flex-wrap gap-2">
          <a
            href={listingsHref(CONSOLE_URL)}
            className="inline-flex min-h-[44px] items-center rounded-pill bg-accent px-4 text-[14px] font-bold text-accent-ink no-underline"
          >
            {t("listCta")}
          </a>
          <a
            href={advertiseHref(CONSOLE_URL)}
            className="inline-flex min-h-[44px] items-center rounded-btn bg-cream px-4 text-[14px] font-bold text-brand-deep no-underline"
          >
            {t("howTo")}
          </a>
        </span>
      </div>
    </div>
  );
}

/**
 * §32/§8a2 — the vendor-acquisition house band, rendered INSIDE the vendor
 * block. First-party copy linking the M5 advertiser wizard, with the rate from
 * config; not a served creative, so deliberately no Sponsored badge and no
 * tracking beacons (same rule as `HouseAdCard`).
 */
export async function AdvertiseBand() {
  const t = await getTranslations("ui.home.advertise");
  return (
    <a
      href={advertiseHref(CONSOLE_URL)}
      data-testid="advertise-band"
      className="mt-2.5 flex items-center gap-3 rounded-card bg-brand-deep p-3.5 text-white no-underline"
    >
      <span aria-hidden="true" className="text-xl">
        📣
      </span>
      <span className="flex-1">
        <b className="block text-[12.5px] font-semibold">{t("title")}</b>
        <small className="text-[10.5px] text-brand-soft-2">
          {t("sub", { price: advertisePrice(t("perWeek")) })}
        </small>
      </span>
      <span className="rounded-pill bg-accent px-3 py-1.5 text-[12px] font-bold text-accent-ink">
        {t("cta")}
      </span>
    </a>
  );
}

/** §10c — FAQ accordion. Native `<details>`, so it works with zero JS; the
 * FAQPage JSON-LD is emitted by the page from these same strings. */
export async function HomeFaq() {
  const t = await getTranslations("ui.home.faq");
  return (
    <Section title={t("title")}>
      <div className="flex flex-col gap-2">
        {(["1", "2", "3", "4"] as const).map((n) => (
          <details key={n} className="rounded-btn border border-cream-line bg-card px-4">
            <summary className="cursor-pointer list-none py-3.5 text-[13px] font-semibold text-ink">
              {t(`q${n}`)}
            </summary>
            <div className="pb-3.5 text-[12px] leading-relaxed text-sub">{t(`a${n}`)}</div>
          </details>
        ))}
      </div>
    </Section>
  );
}

/**
 * §10 — family strip. The theorganic.in tile sits behind config: with the site
 * not live, `ORGANIC_URL` is unset and the tile renders as a non-navigating
 * "coming soon" item rather than a link to nowhere.
 */
export async function FamilyStrip() {
  const t = await getTranslations("ui.home.family");
  return (
    <Section title={t("title")} className="pb-0">
      <EcoStrip>
        <EcoPill href="/" gradient="milk" title="🥛 milk.in" sub={t("milk")} />
        {ORGANIC_URL ? (
          <EcoPill href={ORGANIC_URL} gradient="organic" title="🌿 theorganic.in" sub={t("organic")} />
        ) : (
          <span
            title={t("soon")}
            className="block rounded-card bg-eco-organic px-4 py-3 text-white opacity-80"
          >
            <b className="text-[13px] font-semibold">🌿 theorganic.in</b>
            <small className="block text-[10px]">{t("soon")}</small>
          </span>
        )}
        <EcoPill href="/notifications" gradient="coins" title="🪙 AgriCoins" sub={t("coins")} />
      </EcoStrip>
    </Section>
  );
}
