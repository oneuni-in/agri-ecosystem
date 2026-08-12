import { getTranslations } from "next-intl/server";

import { ListBusinessCta } from "@/components/molecules/ListBusinessCta";

import { NotifyMe } from "./notify-me";

/** Warm empty state for non-TN pincodes (never an error screen) — shared by
 * the landing page and the bare-/{pincode} route, which renders it in place
 * because there is no district to build a /{city}/{pincode} redirect from. */
export async function OutOfArea({ pincode }: { pincode: string }) {
  const t = await getTranslations("ui.results");
  return (
    <main
      className="mx-auto flex w-full max-w-[720px] flex-col gap-3 px-4 py-8"
      data-testid="scope-out-of-area"
    >
      <h1 className="font-display text-[22px] font-extrabold text-ink">{t("outTitle")}</h1>
      <p className="text-[15px] text-sub">{t("outBody", { pincode })}</p>
      <NotifyMe pincode={pincode} />
      <ListBusinessCta />
    </main>
  );
}
