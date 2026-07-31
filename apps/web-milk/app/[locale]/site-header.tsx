import { AuthCluster, NotificationBellIsland } from "@agri/auth-client/react";
import { CoinsBalancePill, HeaderStack } from "@agri/ui";
import { Suspense } from "react";

import { DudhGlyph } from "@/components/atoms/IndicGlyphs";
import { ListBusinessCta } from "@/components/molecules/ListBusinessCta";

import { HeaderLocation } from "./header-location";
import { LocaleSwitcher } from "./locale-switcher";

export function SiteHeader() {
  return (
    <HeaderStack
      logo="milk.in"
      // The Devanagari "दूध" is an inline SVG (`DudhGlyph`), not the literal
      // characters - this tagline renders on every page/locale, and the
      // literal glyph would force ~121 KB of Noto Sans Devanagari onto every
      // English page for text nobody reads as running content (issue #45).
      // பால் (Tamil) stays as real text: en/ta pages already need that font
      // for genuine vernacular content elsewhere, so SVG-ifying it here buys
      // nothing. `DudhGlyph` supplies its own `role="img"`/`aria-label` so
      // the tagline's accessible text is unchanged.
      tagline={
        <>
          Every milk near you · பால் · <DudhGlyph />
        </>
      }
      // `HeaderStack` has no slot besides logo/tagline/location/right. The
      // right cluster is off-limits (see site-footer.tsx's CLS 0.098->0.136
      // note), so the CTA rides in as the first child of `location`: it is a
      // plain server-rendered <a>, not a hydrating island, so it cannot
      // shift as HeaderLocation's client pill hydrates beside it.
      location={
        <>
          <ListBusinessCta variant="header" />
          <HeaderLocation />
        </>
      }
      right={
        <>
          {/* LocaleSwitcher reads useSearchParams() (query-preserving
              switch, final-review fix) - needs a Suspense boundary in a
              static page, same as view-beacon.tsx. */}
          <Suspense fallback={null}>
            <LocaleSwitcher />
          </Suspense>
          <NotificationBellIsland basePath="/api/notify" href="/notifications" label="Notifications" />
          <CoinsBalancePill endpoint="/api/coins/balance" />
          <AuthCluster />
        </>
      }
    />
  );
}
