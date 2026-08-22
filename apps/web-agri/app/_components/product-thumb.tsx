"use client";

import { tintClass, type Tint } from "@agri/ui";
import { useEffect, useRef, useState } from "react";

/**
 * A-U6 — the product media band, shared by the category landing's strip, the
 * product detail gallery and the business profile's catalogue.
 *
 * Generalised from the business profile's `ProductImage`, whose reason for
 * existing is unchanged and worth repeating: `GET /catalog/businesses/{slug}
 * /products` returns media URLs on the object store that answer **403** to an
 * anonymous request, so every thumbnail on a real listing rendered as a
 * broken-image glyph. A grey torn-page icon next to "Dairy Mart Fresh Cow
 * Milk · ₹34/500ml" reads as a broken shop, not a broken bucket — and these
 * pages exist to make a small business look trustworthy.
 *
 * The fallback is the A2 reference's own treatment (`.pcard .media`): a
 * pastel tint band with the produce glyph centred, not a grey box. So a
 * missing photo looks like a design choice rather than a failure, and when
 * the media URLs start resolving the photographs simply appear.
 *
 * The tint is decorative chrome — it carries no meaning and nothing reads it
 * back. It is picked by `tintFor` in the sibling `product-tints.ts`, which is
 * a server-safe module precisely because this one is not.
 */

export function ProductThumb({
  src,
  alt,
  tint = "leaf",
  glyph = "🌾",
  className = "h-[78px]",
  glyphClassName = "text-[32px]",
}: {
  src?: string | null | undefined;
  alt: string;
  tint?: Tint;
  /** The produce glyph shown when there is no usable photograph. */
  glyph?: string;
  /** Height utility for the band — the strip is shorter than the gallery. */
  className?: string;
  glyphClassName?: string;
}) {
  const [failed, setFailed] = useState(false);
  const ref = useRef<HTMLImageElement>(null);

  // `onError` alone is not enough. The server sends the <img> in the HTML, so
  // the browser can request and FAIL it before React hydrates and attaches the
  // handler — which is exactly what happens here, because the media host
  // answers 403 immediately. The listener never fires and the visitor is left
  // looking at a broken-image glyph. This checks the element's own state once
  // on mount: a complete image with zero natural width has already failed.
  useEffect(() => {
    const img = ref.current;
    if (img && img.complete && img.naturalWidth === 0) setFailed(true);
  }, []);

  if (!src || failed) {
    return (
      <div
        aria-hidden="true"
        className={`flex w-full items-center justify-center ${tintClass[tint]} ${className} ${glyphClassName}`}
      >
        {glyph}
      </div>
    );
  }

  return (
    // Media-domain URLs are absolute and configured per environment, so
    // next/image's remote patterns would have to be pinned at build time.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      ref={ref}
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
      className={`w-full object-cover ${className}`}
    />
  );
}
