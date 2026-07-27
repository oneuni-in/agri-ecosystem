"use client";

import { PincodeHeroFinder } from "../../pincode-hero";

/**
 * `page.tsx` here is a Server Component, so it can't pass an inline
 * `hrefForPincode` closure straight to the client-only `PincodeHeroFinder`
 * (functions aren't serializable across the RSC boundary — Next throws at
 * prerender time). This thin client wrapper takes the serializable
 * `category` slug instead and builds the closure on the client.
 */
export function CategoryPincodeFinder({ category }: { category: string }) {
  return <PincodeHeroFinder hrefForPincode={(pincode) => `/${pincode}?category=${category}`} />;
}
