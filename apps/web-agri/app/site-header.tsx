import {
  AuthCluster,
  NotificationBellIsland,
  SignedIn,
} from "@agri/auth-client/react";
import {
  CoinsBalancePill,
  HeaderStack,
  UtilityLink,
  UtilityStrip,
} from "@agri/ui";
import { getTranslations } from "next-intl/server";

import { fetchHelplines } from "@/lib/helplines";

import { BrandLink } from "./brand-link";
import { HeaderLocation } from "./header-location";
import { AgriLocaleSwitcher } from "./locale-switcher";

/**
 * A-U1 §1 + §2 — utility strip and main header, mirroring web-milk's proven
 * `site-header.tsx` structure. No search bar in the header: search lives in
 * the home's §5 band (A1's explicit note).
 *
 * F1 rule: nothing here requires a session secret. The auth cluster renders
 * the guest Login pill without one, SignedIn gates the widgets that would
 * probe authed endpoints, and the whole header renders for a guest — never
 * a 500.
 */
export async function SiteHeader() {
  const t = await getTranslations("ui");
  // §1 hotline chip = the SAME E5 dataset the §13 band renders (0046),
  // one source, never a second literal. A dead read leaves `kcc`
  // undefined and the chip absent — the header still renders (F1).
  const kcc = (await fetchHelplines()).find((h) => h.slug === "kcc");
  return (
    <>
      {/* §1 — utility strip. Static server markup only (milk's CLS lesson:
          nothing above the header may hydrate). Eco links to the sibling
          platforms are part of the tagline slot and hide below 768px, exactly
          like A1's `.util .eco`; the hotline chip stays at every width.
          Wrapped in a labelled nav so the strip lives inside a landmark
          (axe `region`). */}
      <nav aria-label={t("agriHome.utility.navLabel")}>
        <UtilityStrip
          tagline={
            <>
              {t("agriHome.utility.tagline")}
              <span className="ml-3 max-md:hidden">
                <a
                  href="https://milk.in"
                  className="tap-target mr-3 text-brand-soft no-underline"
                >
                  🥛 milk.in
                </a>
                <a
                  href="https://theorganic.in"
                  className="tap-target text-brand-soft no-underline"
                >
                  🌿 theorganic.in
                </a>
              </span>
            </>
          }
          links={
            <>
              <UtilityLink href="/business">
                {t("utility.listBusiness")}
              </UtilityLink>
              <UtilityLink href="/business/ads">
                {t("utility.advertise")}
              </UtilityLink>
            </>
          }
          hotline={
            kcc ? (
              <a href={`tel:${kcc.dial}`} className="no-underline">
                {t("agriHome.utility.hotline", { number: kcc.number })}
              </a>
            ) : null
          }
        />
      </nav>
      <HeaderStack
        flat
        nowrap
        // AG-A64: the wordmark links home everywhere except on `/` itself,
        // where BrandLink renders it as today's plain text (no self-link).
        logo={<BrandLink>agri.in</BrandLink>}
        tagline={t("agriHome.brandTagline")}
        location={<HeaderLocation />}
        right={
          // min-h-11 reserves the AuthCluster pill's 44px BEFORE hydration:
          // the cluster is client-only, and its pill mounting grew the header
          // 55→60px and shifted the whole <main> (0.082 CLS, AG-A8 CI
          // evidence). With the height held, hydration changes width only —
          // ml-auto absorbs that without moving anything below.
          <span className="flex min-h-11 items-center gap-2">
            {/* A1 §2 `.lang` — one tap, visible at every width, never a
                hamburger. */}
            <AgriLocaleSwitcher />
            {/* GUEST STATE (A1 §2 comment, U4 A1 lesson): coins pill and bell
                poll authenticated endpoints, so a guest mounting them ungated
                logs 401 console errors on every page view. SignedIn keeps the
                fetches from ever firing without a session hint — signed out,
                the cluster is exactly: Login pill. */}
            <SignedIn>
              <CoinsBalancePill endpoint="/api/coins/balance" />
              <NotificationBellIsland
                basePath="/api/notify"
                href="/notifications"
                label={t("agriHome.notificationsLabel")}
              />
            </SignedIn>
            {/* A1 `.btn-login`: the guest pill is WHITE on the brand header.
                AuthCluster hardcodes the brand variant (green-on-green here),
                so the wrapper restyles its login button by selector — tokens
                only, no fork of the auth package. */}
            <span className="contents [&_[data-testid=auth-login]]:!min-h-[44px] [&_[data-testid=auth-login]]:!flex-none [&_[data-testid=auth-login]]:!rounded-pill [&_[data-testid=auth-login]]:!bg-card [&_[data-testid=auth-login]]:!px-4 [&_[data-testid=auth-login]]:!text-[13px] [&_[data-testid=auth-login]]:!text-brand-deep">
              <AuthCluster loginLabel={t("auth.login")} />
            </span>
          </span>
        }
      />
    </>
  );
}
