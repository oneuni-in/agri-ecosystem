import {
  ConsoleCheckRow,
  ConsoleGrid2,
  ConsolePanel,
  ConsoleTopbar,
} from "@agri/ui";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";
import { fetchOwnedBusinesses } from "@/lib/console-gates";

import { BillingForm } from "./billing-form";

export const metadata = { title: "Register to advertise", robots: { index: false } };

/**
 * A-U7 W4 — `/business/ads/register`, the A3 reference's advertiser
 * onboarding page (docs/design-reference/agri/agri_pages_console_v1.html
 * #/ads-register).
 *
 * STYLED FULLY, ASKS ONLY WHAT IT CAN KEEP. The reference collects a legal
 * name, business type, GSTIN, PAN, a billing contact, a billing email and
 * two consents. There is no advertiser record behind any of it: the only
 * one of those the platform stores is `buyer_gstin`, and it is a field on
 * the ORDER at checkout, not a profile. So the trade name and the
 * AgriID-verified contact are shown as the facts they already are, GSTIN is
 * remembered for the wizard, and the rest is absent rather than rendered as
 * inputs that would quietly discard what an advertiser typed.
 *
 * The consent checkboxes are absent for a stronger reason than "no column":
 * a consent that is not recorded with a timestamp is not a consent, and a
 * ticked box that writes nowhere is the kind of thing that looks like
 * compliance and is the opposite of it. The advertising terms are stated on
 * this page as the standing rules they are.
 *
 * The two panels the reference gets exactly right — "What you get" and the
 * two promises — are the real reason this page exists, and they are kept in
 * full.
 */
export default async function AdvertiserRegisterPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/ads/register");
  const owned = await fetchOwnedBusinesses();
  const primary = owned[0];
  // The reference prints a masked phone here. The session payload carries no
  // phone at all — deliberately: it holds agriId, name and roles and nothing
  // that identifies a person directly. The AgriID IS the billing identity
  // the reference's "verified via AgriID ✓" line is pointing at, so that is
  // what this shows rather than reaching for a number the console is not
  // given.

  return (
    <main>
      <ConsoleTopbar
        eyebrow="Advertiser onboarding · one AgriID · GST invoicing"
        title="Register to advertise"
        sub="Any verified business can advertise — your AgriID is the account, so there is nothing new to sign up for"
      />

      <ConsoleGrid2>
        <ConsolePanel title="Business & billing details">
          <BillingForm businessName={primary?.name ?? null} agriId={user.agriId} />
        </ConsolePanel>

        <div className="min-w-0 space-y-3">
          <ConsolePanel title="What you get">
            <ConsoleCheckRow marker="⭐">
              Sponsored placement in your categories and pincodes
            </ConsoleCheckRow>
            <ConsoleCheckRow marker="🎯">Target by category × pincode × town tier</ConsoleCheckRow>
            <ConsoleCheckRow marker="📊">
              Impressions, clicks, CTR and spend — split by pincode and category
            </ConsoleCheckRow>
            <ConsoleCheckRow marker="🧾">A GST invoice for every paid campaign</ConsoleCheckRow>
            <ConsoleCheckRow marker="🛡️">
              Frequency-capped delivery, so one viewer is not shown the same ad all day
            </ConsoleCheckRow>
          </ConsolePanel>

          <ConsolePanel title="The two promises we keep">
            <p className="text-xs leading-relaxed text-sub">
              <b className="font-medium text-ink">1 ·</b> Farmers always see “Sponsored” on paid
              placement.
              <br />
              <b className="font-medium text-ink">2 ·</b> Money never moves organic ranking. The
              Recommended label is earned from reviews, response time and verification — it cannot
              be bought. That is why farmers trust what they see here, and why your click-through
              rate stays worth paying for.
            </p>
          </ConsolePanel>

          <ConsolePanel title="Advertising terms">
            {/* Stated, not tick-boxed: a consent nobody records is not a
                consent. These are the standing rules the ad engine already
                enforces, so the page says them plainly. */}
            <p className="text-xs leading-relaxed text-sub">
              Creatives serve only after a person approves them. No tobacco, liquor or
              financial-guarantee advertising. Campaigns that break policy can be paused, and every
              enforcement action is written to an append-only audit log.
            </p>
          </ConsolePanel>
        </div>
      </ConsoleGrid2>
    </main>
  );
}
