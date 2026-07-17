import type { Metadata } from "next";

export interface MetaInput {
  title: string;
  description?: string;
  /** Absolute canonical URL — build with canonicalUrl(). */
  canonical: string;
  siteName?: string;
  noIndex?: boolean;
  ogImage?: string;
}

/** Builds a Next Metadata object with canonical + OG + robots in one place. */
export function buildMetadata(input: MetaInput): Metadata {
  return {
    title: input.title,
    ...(input.description !== undefined && { description: input.description }),
    alternates: { canonical: input.canonical },
    openGraph: {
      title: input.title,
      ...(input.description !== undefined && { description: input.description }),
      url: input.canonical,
      type: "website",
      ...(input.siteName !== undefined && { siteName: input.siteName }),
      ...(input.ogImage !== undefined && { images: [{ url: input.ogImage }] }),
    },
    ...(input.noIndex && { robots: { index: false, follow: true } }),
  };
}

/** Joins base + path safely; strips query/hash and the trailing slash. */
export function canonicalUrl(base: string, path: string): string {
  const cleanBase = base.replace(/\/+$/, "");
  const cleanPath = path.split(/[?#]/, 1)[0] ?? "";
  const joined = `${cleanBase}/${cleanPath.replace(/^\/+/, "")}`;
  return joined.length > cleanBase.length + 1 ? joined.replace(/\/+$/, "") : cleanBase;
}

/**
 * "Noindex-until-populated" (Execution Schedule §0.6): thin pages self-noindex
 * until they have at least `minimum` items of real content.
 */
export function shouldNoIndex(contentCount: number, minimum = 1): boolean {
  return contentCount < minimum;
}
