/**
 * Robots noindex as a component — React 19 hoists <meta> into <head>.
 * Prefer buildMetadata({ noIndex: true }) for static pages; use this where
 * the decision is data-driven at render time (shouldNoIndex(count)).
 */
export function NoIndex() {
  return <meta name="robots" content="noindex, follow" />;
}
