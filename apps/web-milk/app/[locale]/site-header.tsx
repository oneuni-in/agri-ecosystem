import { AuthCluster, NotificationBellIsland } from "@agri/auth-client/react";
import { CoinsBalancePill, HeaderStack, UtilityLink, UtilityStrip } from "@agri/ui";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { DudhGlyph } from "@/components/atoms/IndicGlyphs";
import { CONSOLE_URL, listingsHref } from "@/lib/console";
import { WHATSAPP_HOTLINE, advertiseHref, hotlineHref } from "@/lib/contact";

import { HeaderLocation } from "./header-location";
import { LocaleSwitcher } from "./locale-switcher";

export async function SiteHeader() {
  const t = await getTranslations("ui");
  return (
    <>
      {/* U1 §1 — utility strip. Static server markup only: it sits above the
          header, so anything that hydrates here would push the whole page
          down as it populates. */}
      <UtilityStrip
        tagline={
          <>
            Every milk near you · பால் · <DudhGlyph />
          </>
        }
        links={
          <>
            {/* The D16 claim/create flow in the Business Console — a door,
                not a new flow. Moved here out of the header row, where a
                fourth item measurably cost CLS (see site-footer.tsx). */}
            <UtilityLink href={listingsHref(CONSOLE_URL)}>{t("utility.listBusiness")}</UtilityLink>
            <UtilityLink href={advertiseHref(CONSOLE_URL)}>{t("utility.advertise")}</UtilityLink>
          </>
        }
        // §1: the slot renders even when the number is unset — the chip
        // itself is simply absent, never an empty golden box.
        hotline={
          WHATSAPP_HOTLINE ? (
            <a href={hotlineHref(WHATSAPP_HOTLINE)} className="no-underline">
              {t("utility.hotline", { number: WHATSAPP_HOTLINE })}
            </a>
          ) : null
        }
      />
      <HeaderStack
        flat
        nowrap
        logo="milk.in"
        // The Devanagari "दूध" is an inline SVG (`DudhGlyph`), not the literal
        // characters - this tagline renders on every page/locale, and the
        // literal glyph would force ~121 KB of Noto Sans Devanagari onto every
        // English page for text nobody reads as running content (issue #45).
        // பால் (Tamil) stays as real text: en/ta pages already need that font
        // for genuine vernacular content elsewhere, so SVG-ifying it here buys
        // nothing. `DudhGlyph` supplies its own `role="img"`/`aria-label` so
        // the tagline's accessible text is unchanged.
        // On a 360px phone the header is one row carrying the location pill,
        // the language switcher and the auth cluster; the full tagline does
        // not fit beside them, and the utility strip directly above already
        // says it in full. So the mother-tongue half stays at every width and
        // the English half joins from `sm` up — the mobile reference snapshot
        // shows exactly "பால் · दूध" here.
        tagline={
          <>
            பால் · <DudhGlyph />
            <span className="max-sm:hidden"> · every milk near you</span>
          </>
        }
        location={<HeaderLocation />}
        right={
          <>
            {/* LocaleSwitcher reads useSearchParams() (query-preserving
                switch, final-review fix) - needs a Suspense boundary in a
                static page, same as view-beacon.tsx. U1 §28 keeps it visible
                on mobile: one tap, never buried in a burger menu. */}
            <Suspense fallback={null}>
              <LocaleSwitcher />
            </Suspense>
            <CoinsBalancePill endpoint="/api/coins/balance" />
            <NotificationBellIsland basePath="/api/notify" href="/notifications" label="Notifications" />
            <AuthCluster />
          </>
        }
      />
    </>
  );
}
