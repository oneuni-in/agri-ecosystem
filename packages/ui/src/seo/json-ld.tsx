// Server-only: JSON-LD lives in typed components (Execution Schedule §0.6).
// NO "use client" anywhere under src/seo/.
import type {
  BreadcrumbList,
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
