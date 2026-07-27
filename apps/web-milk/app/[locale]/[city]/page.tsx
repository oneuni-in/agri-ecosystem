import { citySlug } from "@agri/ui/seo";
import type { Metadata } from "next";
import { setRequestLocale } from "next-intl/server";
import { notFound, permanentRedirect } from "next/navigation";

import { fetchMilkHome } from "@/lib/milk";

import { OutOfArea } from "./[pincode]/out-of-area";

export const revalidate = 300;

const PIN_RE = /^\d{6}$/;

/** This route only ever 301s (legacy /{pincode} URLs), 404s (bare city
 * slugs — no city landing, YAGNI), or shows the out-of-area state — never
 * indexable content: that lives at /{city}/{pincode}. */
export const metadata: Metadata = { title: "Milk.in", robots: { index: false, follow: true } };

export default async function CityOrLegacyPincodePage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; city: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale, city } = await params;
  setRequestLocale(locale);
  if (!PIN_RE.test(city)) notFound();
  const pincode = city; // legacy /{pincode} URL (pre-D28 shape, still linked)
  const data = await fetchMilkHome(pincode);
  if (!data) notFound(); // backend unreachable — matches the old page's behavior
  if (data.location) {
    const sp = await searchParams;
    const qs = new URLSearchParams(
      Object.entries(sp).flatMap(([k, v]) =>
        typeof v === "string" ? [[k, v] as [string, string]] : [],
      ),
    ).toString();
    permanentRedirect(`/${citySlug(data.location.district)}/${pincode}${qs ? `?${qs}` : ""}`);
  }
  return <OutOfArea pincode={pincode} />;
}
