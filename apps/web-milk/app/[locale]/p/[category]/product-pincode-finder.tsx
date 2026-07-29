"use client";

import { PincodeHeroFinder } from "../../pincode-hero";

/**
 * `page.tsx` here is a Server Component, so it cannot pass an inline
 * `hrefForPincode` closure to the client-only `PincodeHeroFinder`
 * (functions are not serializable across the RSC boundary — Next throws at
 * prerender time). This thin client wrapper takes the serializable category
 * value and builds the closure on the client. Mirrors
 * `app/[locale]/c/[category]/category-pincode-finder.tsx`.
 */
export function ProductPincodeFinder({ category }: { category: string }) {
  return (
    <PincodeHeroFinder
      hrefForPincode={(pincode) => `/${pincode}?product_category=${category}`}
    />
  );
}
