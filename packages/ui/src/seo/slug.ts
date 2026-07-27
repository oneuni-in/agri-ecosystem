/** URL slug for a geo district name (the "city" segment of /{city}/{pincode}).
 * Pure + deterministic: the same district name must always yield the same
 * slug, because these URLs are immutable once indexed. */
export function citySlug(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
