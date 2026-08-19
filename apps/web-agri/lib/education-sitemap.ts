import {
  fetchGuides,
  fetchInstitutions,
  fetchResources,
  fetchStates,
  type InstitutionCard,
  type ResourceCard,
} from "./education";

/**
 * The education vertical's sitemap entries.
 *
 * ONLY VERIFIED, ACTIVE INSTITUTIONS. A `listed` college page is `noindex`,
 * and advertising a self-noindexed page to Google is precisely the failure the
 * commodity sitemap's comment already warns about. The rule is stated once
 * here and derived from the same two fields the page's own noindex uses.
 *
 * The walk PAGES. A single unpaged call would cap the sitemap at the API's
 * default of 20 colleges out of 772, and nothing would fail — the file would
 * just be quietly, wrongly short.
 */
const PAGE_LIMIT = 100;

/** Bounded so a cursor bug cannot spin forever during a build. 772 rows at
 * 100 a page is 8; 40 is slack for a corpus several times larger, and hitting
 * it means something is wrong rather than that the corpus grew. */
const MAX_PAGES = 40;

export interface SitemapEntry {
  path: string;
  lastModified?: string;
}

function indexable(college: InstitutionCard): boolean {
  return college.trust === "verified" && college.status === "active";
}

async function allInstitutions(): Promise<InstitutionCard[]> {
  const out: InstitutionCard[] = [];
  let cursor: string | undefined;

  for (let page = 0; page < MAX_PAGES; page += 1) {
    const result = await fetchInstitutions({
      limit: PAGE_LIMIT,
      ...(cursor ? { cursor } : {}),
    });
    out.push(...result.items);
    if (!result.next_cursor) return out;
    cursor = result.next_cursor;
  }
  // Ran out of pages rather than out of rows. Return what we have -- a short
  // sitemap is better than a failed build -- but the truncation is real and
  // should be visible.
  console.warn(
    `[education sitemap] stopped at ${MAX_PAGES} pages (${out.length} rows); cursor did not terminate`,
  );
  return out;
}

async function allResources(kind: "scholarship" | "exam"): Promise<ResourceCard[]> {
  const out: ResourceCard[] = [];
  let cursor: string | undefined;

  for (let page = 0; page < MAX_PAGES; page += 1) {
    const result = await fetchResources({
      kind,
      limit: PAGE_LIMIT,
      ...(cursor ? { cursor } : {}),
    });
    out.push(...result.items);
    if (!result.next_cursor) return out;
    cursor = result.next_cursor;
  }
  return out;
}

export async function educationSitemapEntries(): Promise<SitemapEntry[]> {
  const [states, colleges, scholarships, exams, guides] = await Promise.all([
    fetchStates(),
    allInstitutions(),
    allResources("scholarship"),
    allResources("exam"),
    fetchGuides(),
  ]);

  // Every list read degrades to empty on failure (F1), so a dead engine
  // shrinks the sitemap rather than failing the build -- the contract the
  // commodity entries already follow.
  return [
    { path: "/colleges" },
    ...states.map((state) => ({ path: `/colleges/state/${state.slug}` })),
    // `lastModified` is the data's own stamp, never the build time: an honest
    // lastModified is the one the row carries.
    ...colleges
      .filter(indexable)
      .map((college) => ({
        path: `/colleges/${college.slug}`,
        lastModified: college.last_verified_at,
      })),
    { path: "/scholarships" },
    ...scholarships.map((row) => ({
      path: `/scholarships/${row.slug}`,
      lastModified: row.last_verified_at,
    })),
    { path: "/exams" },
    ...exams.map((row) => ({ path: `/exams/${row.slug}`, lastModified: row.last_verified_at })),
    { path: "/counselling" },
    { path: "/study-abroad" },
    ...guides.map((guide) => ({
      path: `/guides/${guide.slug}`,
      lastModified: guide.last_verified_at,
    })),
  ];
}
