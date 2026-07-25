"use client";

import { Button, Card } from "@agri/ui";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import type { NearbyBranch } from "@/lib/business";

const PIN_RE = /^\d{6}$/;
// distance_m sentinel for a branch we couldn't geocode (shared with the
// backend's UNLOCATABLE_M) - hide the distance line rather than show a
// billion-metre reading.
const UNLOCATABLE_M = 1_000_000_000;

// Copied verbatim from lead-form.tsx's field styling (D16/D27 idiom) so this
// form reads as the same system as the enquiry form below it on this page.
const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";
const LABEL = "block text-[13px] font-semibold text-ink";

/**
 * Brand-page "shops near you" (D27 Task 14): client island so a pincode edit
 * can refetch without a page reload. Server renders the page around this
 * with `revalidate = 300` intact - fetching happens after mount, so the
 * static shell is unaffected. Consumes the public nearby-branches route
 * (backend `public=True`) via the shared `/api/directory` proxy, which
 * carves out this one GET path from its default auth gate (see the proxy's
 * own comment) so guests - most brand-page visitors - get results too.
 */
export function NearbyShops({
  slug,
  initialPincode,
}: {
  slug: string;
  initialPincode: string;
}) {
  const t = useTranslations("ui.brandPage");
  const [pincode, setPincode] = useState(initialPincode);
  const [items, setItems] = useState<NearbyBranch[] | null>(null);
  const [busy, setBusy] = useState(false);

  const search = useCallback(
    async (pin: string) => {
      if (!PIN_RE.test(pin)) return;
      setBusy(true);
      try {
        const response = await fetch(
          `/api/directory/businesses/${encodeURIComponent(slug)}/nearby-branches?pincode=${pin}`,
        );
        setItems(
          response.ok ? ((await response.json()) as { items: NearbyBranch[] }).items : [],
        );
      } catch {
        setItems([]);
      } finally {
        setBusy(false);
      }
    },
    [slug],
  );

  useEffect(() => {
    void search(initialPincode);
  }, [initialPincode, search]);

  return (
    <section className="mt-6 space-y-2.5" aria-labelledby="nearby-shops-h">
      <h2 id="nearby-shops-h" className="font-display text-[16px] font-extrabold text-ink">
        {t("shopsNearYou")}
      </h2>
      <form
        className="space-y-2"
        onSubmit={(event) => {
          event.preventDefault();
          void search(pincode);
        }}
      >
        <label className={LABEL}>
          {t("pincodeLabel")}
          <input
            required
            inputMode="numeric"
            pattern="\d{6}"
            maxLength={6}
            value={pincode}
            onChange={(event) => setPincode(event.target.value.replace(/\D/g, "").slice(0, 6))}
            className={FIELD}
          />
        </label>
        <Button
          type="submit"
          variant="brand"
          disabled={busy || !PIN_RE.test(pincode)}
          className="max-w-[200px]"
        >
          {t("find")}
        </Button>
      </form>
      {items && items.length === 0 ? (
        <p className="text-[13px] text-sub">{t("empty", { pincode })}</p>
      ) : null}
      {items && items.length > 0 ? (
        <ul className="space-y-2">
          {items.map((branch) => (
            <li key={branch.id}>
              <Card className="space-y-1 p-3">
                <p className="text-[13.5px] font-semibold text-ink">{branch.address}</p>
                <p className="text-[12.5px] text-sub">
                  {branch.district}, {branch.state} {branch.pincode}
                  {branch.distance_m < UNLOCATABLE_M
                    ? ` · ${t("kmAway", { km: (branch.distance_m / 1000).toFixed(1) })}`
                    : ""}
                </p>
              </Card>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
