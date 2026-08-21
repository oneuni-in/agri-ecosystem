import { ConsoleShell } from "@agri/ui";
import { getTranslations } from "next-intl/server";

import { auth } from "@/lib/auth";
import { ACCOUNT_MODULES, resolveModuleHref } from "@/lib/account-modules";
import { fetchAccountIdentity, handleLabel } from "@/lib/account-identity";
import { languageName } from "@/lib/languages";

import { AccountNavLinks } from "./account-nav-links";

/**
 * The /account shell (AG-U5 P1).
 *
 * ONE dashboard, mounting what already ships. The modules underneath —
 * enquiries, saved, coins, notifications — are not rebuilt here; this layout
 * owns navigation and nothing else, which is why the only thing it fetches is
 * the identity card's data.
 *
 * NO AUTH GATE HERE, on purpose, and for a different reason than
 * `business/layout.tsx` has. The console is covered by `middleware.ts`, whose
 * matcher is `/business/:path*`; /account is deliberately NOT in that matcher
 * because AG-U5's guest state is a real state — a signed-out visitor is meant
 * to reach /account and be told what an account is for, not be bounced to a
 * login screen that explains nothing. Each sub-page keeps its own
 * authoritative `if (!user) redirect(...)`, which is where the gate belongs:
 * a layout-level redirect could only ever carry `next=/account`, losing the
 * deep link the visitor actually asked for.
 *
 * A guest therefore gets the children with no sidebar. Rendering ten links to
 * pages that would each bounce them is not navigation, it is a maze.
 */
export default async function AccountLayout({ children }: { children: React.ReactNode }) {
  const [t, user] = await Promise.all([getTranslations("ui.account"), auth.getServerUser()]);
  const token = user ? await auth.getAccessToken() : null;
  const identity = token ? await fetchAccountIdentity(token) : null;

  if (!identity) {
    return <div className="mx-auto w-full max-w-5xl px-4 py-6">{children}</div>;
  }

  const idOrigin = process.env.ID_PUBLIC_ORIGIN ?? "http://localhost:3003";
  const entries = ACCOUNT_MODULES.map((entry) => ({
    ...entry,
    href: resolveModuleHref(entry, idOrigin),
    title: t(`nav.${entry.id}`),
  }));

  // Pincode and language, each dropped when unknown rather than rendered as a
  // dash. "641001 · தமிழ்" is a fact; "— · —" is furniture.
  const meta = [identity.pincode, languageName(identity.language), "AgriID"].filter(Boolean);

  return (
    <ConsoleShell
      navLabel={t("heading")}
      heading={t("heading")}
      nav={
        <>
          <div className="mb-3 hidden items-center gap-2.5 rounded-card border border-cream-line bg-card px-3 py-2.5 sm:flex">
            <span
              aria-hidden="true"
              className="flex h-8 w-8 flex-none items-center justify-center rounded-pill bg-brand-soft font-display text-[14px] font-extrabold text-brand-deep"
            >
              {(identity.name ?? identity.agriId).slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0">
              <b className="block truncate font-display text-[13px] font-extrabold text-ink">
                {handleLabel(identity.agriId, identity.handleIsFallback)}
              </b>
              <small className="block truncate text-[11px] text-muted">{meta.join(" · ")}</small>
            </span>
          </div>
          <AccountNavLinks entries={entries} settingsLabel={t("settings")} />
          <p className="mt-4 hidden text-[10.5px] leading-relaxed text-muted sm:block">
            {t("idNote")}
          </p>
        </>
      }
    >
      {children}
    </ConsoleShell>
  );
}
