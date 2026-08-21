"use client";

import { tintClass, type Tint } from "@agri/ui";
import { useCallback, useState } from "react";

/**
 * A-U6 W2 — the A2 reference's `.gallery`: a 240px main image over a row of
 * selectable thumbs.
 *
 * A client island only because selecting a thumb is state. The FIRST image is
 * server-rendered inside it, so the product's photograph is in the SSR HTML
 * and does not wait on hydration to paint.
 *
 * Failure handling matches `ProductThumb`, and for the same reason: the media
 * host answers 403 to anonymous requests, and the image can fail before React
 * attaches `onError`, so the handler never fires. Every <img> here therefore
 * goes through `markIfBroken`, a CALLBACK ref that inspects the element the
 * moment React attaches it — `complete && naturalWidth === 0` is an image
 * that has already finished and has no pixels. A useEffect on the main image
 * alone was not enough: the thumbs mount at the same time and failed the
 * same way, which is exactly what the first screenshot showed.
 * A failed image falls back to the tinted band with the produce glyph rather
 * than a broken-image icon.
 *
 * With no images at all the thumb row is absent, not an empty strip — one
 * photograph is not a gallery and should not look like a broken one.
 */
export function Gallery({
  images,
  alt,
  tint = "leaf",
  glyph = "🌾",
}: {
  images: string[];
  alt: string;
  tint?: Tint;
  glyph?: string;
}) {
  const [index, setIndex] = useState(0);
  const [failed, setFailed] = useState<Record<number, boolean>>({});

  const src = images[index];
  const broken = failed[index] === true;

  const fail = useCallback(
    (i: number) => setFailed((prev) => (prev[i] ? prev : { ...prev, [i]: true })),
    [],
  );
  /** Catches an image that already errored before hydration. */
  const markIfBroken = useCallback(
    (i: number) => (img: HTMLImageElement | null) => {
      if (img && img.complete && img.naturalWidth === 0) fail(i);
    },
    [fail],
  );

  return (
    <div className="rounded-card border border-cream-line bg-card p-3.5">
      {src && !broken ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          ref={markIfBroken(index)}
          key={src}
          src={src}
          alt={alt}
          className="h-[240px] w-full rounded-btn object-cover"
          onError={() => fail(index)}
        />
      ) : (
        <div
          aria-hidden="true"
          className={`flex h-[240px] w-full items-center justify-center rounded-btn text-[96px] ${tintClass[tint]}`}
        >
          {glyph}
        </div>
      )}

      {images.length > 1 ? (
        <div className="mt-2.5 flex gap-2" role="group" aria-label="Product images">
          {images.map((image, i) => (
            <button
              key={image}
              type="button"
              aria-label={`${alt} — image ${i + 1}`}
              aria-current={i === index ? "true" : undefined}
              onClick={() => setIndex(i)}
              className={`tap-target h-[52px] flex-1 overflow-hidden rounded-[9px] border ${
                i === index ? "border-brand bg-brand-soft" : "border-cream-line bg-cream-deep"
              }`}
            >
              {failed[i] ? (
                <span aria-hidden="true" className="flex h-full items-center justify-center text-[22px]">
                  {glyph}
                </span>
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  ref={markIfBroken(i)}
                  src={image}
                  alt=""
                  loading="lazy"
                  onError={() => fail(i)}
                  className="h-full w-full object-cover"
                />
              )}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
