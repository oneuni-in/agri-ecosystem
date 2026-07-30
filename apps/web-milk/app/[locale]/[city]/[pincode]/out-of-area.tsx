import { ListBusinessCta } from "@/components/molecules/ListBusinessCta";

import { NotifyMe } from "./notify-me";

/** Warm empty state for non-TN pincodes (never an error screen) — shared by
 * the landing page and the bare-/{pincode} route, which renders it in place
 * because there is no district to build a /{city}/{pincode} redirect from. */
export function OutOfArea({ pincode }: { pincode: string }) {
  return (
    <main
      className="mx-auto flex w-full max-w-[720px] flex-col gap-3 px-4 py-8"
      data-testid="scope-out-of-area"
    >
      <h1 className="font-display text-[22px] font-extrabold text-ink">
        We&apos;re live in Tamil Nadu right now
      </h1>
      <p className="text-[15px] text-sub">
        {pincode} isn&apos;t in our coverage yet — more areas coming soon. Leave your number and
        we&apos;ll reach out the moment milk vendors arrive.
      </p>
      <NotifyMe pincode={pincode} />
      <ListBusinessCta />
    </main>
  );
}
