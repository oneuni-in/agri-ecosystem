import { Eyebrow } from "@agri/ui";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";
import { fetchAccountIdentity } from "@/lib/account-identity";

/**
 * /account — the dashboard overview (AG-U5 P1).
 *
 * P1 ships the shell and this header only. The stats row, enquiries panel,
 * price-alert manager, saved rail and crops panel are P2's, and each arrives
 * reading real data — a placeholder card here would have to be deleted before
 * it was ever true, and would sit in P1's proof pair pretending otherwise.
 *
 * `noindex`: one person's dashboard has nothing to offer a crawler.
 */
export const metadata: Metadata = { title: "Your account", robots: { index: false } };

export const dynamic = "force-dynamic";

export default async function AccountOverviewPage() {
  const user = await auth.getServerUser();
  // P6 replaces this with the guest state the reference draws (no identity
  // renders, Login in the header). Until then a signed-out visitor goes where
  // every other account surface sends them, carrying /account as `next`.
  if (!user) redirect("/api/auth/login?next=/account");

  const [t, token] = await Promise.all([getTranslations("ui.account"), auth.getAccessToken()]);
  const identity = token ? await fetchAccountIdentity(token) : null;
  // The layout already degraded to a bare shell if this read failed; a stale
  // cookie that survived getServerUser() lands here, and login is the fix.
  if (!identity) redirect("/api/auth/login?next=/account");

  const place = [identity.district, identity.pincode].filter(Boolean).join(" · ");

  return (
    <div className="pb-4">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0">
          <Eyebrow>{t("eyebrow")}</Eyebrow>
          <h1 className="mt-1 font-display text-[22px] font-extrabold leading-tight text-ink sm:text-[26px]">
            {identity.name ? t("greeting", { name: identity.name }) : t("greetingNoName")}
          </h1>
          {place ? <p className="mt-1 text-[13px] text-sub">{place}</p> : null}
        </div>
        <span className="flex-1" />
        <Link
          href="/"
          prefetch={false}
          className="tap-target inline-flex items-center rounded-pill border border-cream-line px-3.5 py-2 text-[12.5px] font-semibold text-ink no-underline"
        >
          {t("back")}
        </Link>
      </div>
    </div>
  );
}
