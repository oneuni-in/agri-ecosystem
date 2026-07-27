// Server components — zero "use client" in this module.
export {
  breadcrumbJsonLd,
  datasetJsonLd,
  faqPageJsonLd,
  JsonLd,
  localBusinessJsonLd,
  productJsonLd,
} from "./json-ld";
export type {
  BreadcrumbItem,
  DatasetInput,
  FaqInput,
  LocalBusinessInput,
  ProductInput,
} from "./json-ld";
export { buildMetadata, canonicalUrl, shouldNoIndex } from "./meta";
export type { MetaInput } from "./meta";
export { NoIndex } from "./no-index";
export { citySlug } from "./slug";
