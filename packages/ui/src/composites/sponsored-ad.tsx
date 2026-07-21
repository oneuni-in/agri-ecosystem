"use client";

/**
 * The ad render contract (D21 non-negotiable 1): every served ad carries the
 * "★ Sponsored" badge - <Badge variant="sponsored"> type-forbids children, so
 * the label text cannot be overridden or omitted. Copy is plain text (React
 * escaping; never dangerouslySetInnerHTML). Impression fires once per mount.
 */
import { useEffect, useRef } from "react";

import { Badge } from "../components/badge";
import { Card } from "../components/card";
import type { ServedAd } from "../lib/sponsored";

export function SponsoredAd({
  ad,
  onImpression,
  onClick,
}: {
  ad: ServedAd;
  onImpression: () => void;
  onClick: () => void;
}) {
  const fired = useRef(false);
  useEffect(() => {
    if (fired.current) return;
    fired.current = true;
    onImpression();
  }, [onImpression]);

  return (
    <Card>
      <div className="flex flex-col gap-2 p-3">
        <Badge variant="sponsored" />
        {ad.media_urls[0] ? (
          <img
            src={ad.media_urls[0]}
            alt={ad.title}
            className="max-h-40 w-full rounded-lg object-cover"
          />
        ) : null}
        <a
          href={ad.target_url}
          target="_blank"
          rel="noopener nofollow sponsored"
          onClick={onClick}
          className="flex flex-col gap-1"
        >
          <span className="text-sm font-extrabold">{ad.title}</span>
          <span className="text-xs text-sub">{ad.body}</span>
        </a>
      </div>
    </Card>
  );
}
