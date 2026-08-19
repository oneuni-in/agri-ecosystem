"use client";

import { useState } from "react";

/**
 * A product thumbnail that degrades to the crop tile instead of a broken
 * image icon.
 *
 * This is not defensive padding. `GET /catalog/businesses/{slug}/products`
 * currently returns media URLs on the object store that answer **403** to an
 * anonymous request, so every thumbnail on a real listing rendered as a
 * broken-image glyph. A grey torn-page icon next to "Dairy Mart Fresh Cow
 * Milk · ₹34/500ml" reads as a broken shop, not a broken bucket — and this
 * page's whole job is to make a small business look trustworthy.
 *
 * When the media URLs start resolving this component does nothing and the
 * photographs simply appear. It is worth keeping regardless: one product
 * whose file went missing should cost that product its picture, not the
 * shop its credibility.
 */
export function ProductImage({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div
        aria-hidden="true"
        className="flex h-[104px] w-full items-center justify-center bg-cream text-[26px]"
      >
        🌾
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
      className="h-[104px] w-full object-cover"
    />
  );
}
