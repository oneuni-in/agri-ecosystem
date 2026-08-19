// Server-only: JSON-LD lives in typed components (Execution Schedule §0.6).
// NO "use client" anywhere under src/seo/.
import type {
  BreadcrumbList,
  CollegeOrUniversity,
  Dataset,
  FAQPage,
  LocalBusiness,
  Product,
  Thing,
  WithContext,
} from "schema-dts";

/**
 * Renders a JSON-LD script tag. `data` must be a WithContext<Thing> produced
 * by the builders below — invalid shapes fail typecheck.
 */
export function JsonLd<T extends Thing>({ data }: { data: WithContext<T> }) {
  return (
    <script
      type="application/ld+json"
      // `<` is escaped so user content can never close the script tag.
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replaceAll("<", "\\u003c") }}
    />
  );
}

export interface LocalBusinessInput {
  name: string;
  url: string;
  telephone?: string;
  address: {
    locality: string;
    region: string;
    postalCode?: string;
  };
  geo?: { latitude: number; longitude: number };
  aggregateRating?: { ratingValue: number; ratingCount: number };
}

export function localBusinessJsonLd(input: LocalBusinessInput): WithContext<LocalBusiness> {
  return {
    "@context": "https://schema.org",
    "@type": "LocalBusiness",
    name: input.name,
    url: input.url,
    ...(input.telephone !== undefined && { telephone: input.telephone }),
    address: {
      "@type": "PostalAddress",
      addressLocality: input.address.locality,
      addressRegion: input.address.region,
      ...(input.address.postalCode !== undefined && { postalCode: input.address.postalCode }),
      addressCountry: "IN",
    },
    ...(input.geo && {
      geo: { "@type": "GeoCoordinates", latitude: input.geo.latitude, longitude: input.geo.longitude },
    }),
    ...(input.aggregateRating && {
      aggregateRating: {
        "@type": "AggregateRating",
        ratingValue: input.aggregateRating.ratingValue,
        ratingCount: input.aggregateRating.ratingCount,
      },
    }),
  };
}

export interface ProductInput {
  name: string;
  url: string;
  brand?: string;
  image?: string;
  offers?: { price: number; priceCurrency: "INR" };
  aggregateRating?: { ratingValue: number; ratingCount: number };
}

export function productJsonLd(input: ProductInput): WithContext<Product> {
  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: input.name,
    url: input.url,
    ...(input.brand !== undefined && { brand: { "@type": "Brand", name: input.brand } }),
    ...(input.image !== undefined && { image: input.image }),
    ...(input.offers && {
      offers: {
        "@type": "Offer",
        price: input.offers.price,
        priceCurrency: input.offers.priceCurrency,
      },
    }),
    ...(input.aggregateRating && {
      aggregateRating: {
        "@type": "AggregateRating",
        ratingValue: input.aggregateRating.ratingValue,
        ratingCount: input.aggregateRating.ratingCount,
      },
    }),
  };
}

export interface FaqInput {
  questions: readonly { question: string; answer: string }[];
}

export function faqPageJsonLd(input: FaqInput): WithContext<FAQPage> {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: input.questions.map((q) => ({
      "@type": "Question",
      name: q.question,
      acceptedAnswer: { "@type": "Answer", text: q.answer },
    })),
  };
}

export interface BreadcrumbItem {
  name: string;
  url: string;
}

export function breadcrumbJsonLd(items: readonly BreadcrumbItem[]): WithContext<BreadcrumbList> {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: item.name,
      item: item.url,
    })),
  };
}

export interface DatasetInput {
  name: string;
  description: string;
  url: string;
  license?: string;
}

export function datasetJsonLd(input: DatasetInput): WithContext<Dataset> {
  return {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name: input.name,
    description: input.description,
    url: input.url,
    ...(input.license !== undefined && { license: input.license }),
  };
}


export interface CollegeInput {
  name: string;
  url: string;
  /** Optional throughout below the name and URL: the corpus records an address
   * for some institutions and not others, and schema.org markup asserting a
   * postal address we do not have is a claim, not a blank. */
  telephone?: string;
  email?: string;
  website?: string;
  foundingDate?: string;
  address?: {
    streetAddress?: string;
    locality?: string;
    region?: string;
    postalCode?: string;
  };
  geo?: { latitude: number; longitude: number };
}

/**
 * `CollegeOrUniversity` + `PostalAddress` for an agri-colleges detail page.
 *
 * RENDER THIS ON VERIFIED PAGES ONLY. A `listed` row came from a bulk national
 * directory and was never checked against the institution's own page; marking
 * one up as a CollegeOrUniversity with an address nobody confirmed is exactly
 * the kind of claim that earns a manual action. The caller decides — this
 * builder cannot know the trust level, so the rule lives at the call site and
 * is stated there too.
 *
 * There is deliberately no builder for scholarships or exams: schema.org has
 * no honest type for either, and marking one up as something it is not invites
 * the same problem (spec §6).
 */
export function collegeJsonLd(input: CollegeInput): WithContext<CollegeOrUniversity> {
  const address = input.address;
  const hasAddress =
    address !== undefined &&
    (address.streetAddress ?? address.locality ?? address.region ?? address.postalCode) !==
      undefined;

  return {
    "@context": "https://schema.org",
    "@type": "CollegeOrUniversity",
    name: input.name,
    url: input.url,
    ...(input.telephone !== undefined && { telephone: input.telephone }),
    ...(input.email !== undefined && { email: input.email }),
    ...(input.website !== undefined && { sameAs: input.website }),
    ...(input.foundingDate !== undefined && { foundingDate: input.foundingDate }),
    ...(hasAddress && {
      address: {
        "@type": "PostalAddress" as const,
        ...(address.streetAddress !== undefined && { streetAddress: address.streetAddress }),
        ...(address.locality !== undefined && { addressLocality: address.locality }),
        ...(address.region !== undefined && { addressRegion: address.region }),
        ...(address.postalCode !== undefined && { postalCode: address.postalCode }),
        addressCountry: "IN",
      },
    }),
    ...(input.geo && {
      geo: {
        "@type": "GeoCoordinates" as const,
        latitude: input.geo.latitude,
        longitude: input.geo.longitude,
      },
    }),
  };
}
