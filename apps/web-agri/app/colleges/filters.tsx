import Link from "next/link";

/**
 * Server-rendered filter links, following `/directory` rather than the client
 * island the plan sketched: no JS shipped, works with JS off, crawlable, and
 * the URL is the state. That matters most on this page — `/colleges` carries
 * the 0.90 throttled-3G floor with no carve-out, and an island is exactly the
 * kind of thing that spends the budget.
 *
 * There is deliberately NO district control. `geo.districts` holds 38 rows,
 * all Tamil Nadu, until D65, so a district filter anywhere else returns an
 * empty list — which reads as "no colleges here" when the truth is "we do not
 * have that data yet". Those mean opposite things to a student.
 */
export interface FilterState {
  gov?: string | undefined;
  trust?: string | undefined;
  q?: string | undefined;
}

function chipClass(active: boolean): string {
  return `tap-target inline-flex items-center rounded-pill border px-3.5 text-[12.5px] font-semibold no-underline ${
    active ? "border-brand bg-brand text-white" : "border-cream-line bg-card text-ink"
  }`;
}

/** Rebuild the query string with one key changed, dropping it when it is
 * being turned off. Keeps every OTHER active filter, which a naive
 * `?gov=true` link would silently discard. */
function hrefWith(base: string, current: FilterState, patch: FilterState): string {
  const merged: Record<string, string> = {};
  for (const [key, value] of Object.entries({ ...current, ...patch })) {
    if (value) merged[key] = value;
  }
  const query = new URLSearchParams(merged).toString();
  return query ? `${base}?${query}` : base;
}

export function CollegeFilters({
  base,
  current,
  labels,
}: {
  base: string;
  current: FilterState;
  labels: {
    filterLabel: string;
    all: string;
    government: string;
    private: string;
    verifiedOnly: string;
    searchLabel: string;
    searchPlaceholder: string;
    searchSubmit: string;
  };
}) {
  return (
    <>
      <div
        className="mt-4 flex flex-wrap gap-2"
        role="navigation"
        aria-label={labels.filterLabel}
      >
        <Link
          href={hrefWith(base, current, { gov: undefined })}
          prefetch={false}
          aria-current={current.gov ? undefined : "page"}
          className={chipClass(!current.gov)}
        >
          {labels.all}
        </Link>
        <Link
          href={hrefWith(base, current, { gov: "true" })}
          prefetch={false}
          aria-current={current.gov === "true" ? "page" : undefined}
          className={chipClass(current.gov === "true")}
        >
          {labels.government}
        </Link>
        <Link
          href={hrefWith(base, current, { gov: "false" })}
          prefetch={false}
          aria-current={current.gov === "false" ? "page" : undefined}
          className={chipClass(current.gov === "false")}
        >
          {labels.private}
        </Link>
        <Link
          href={hrefWith(base, current, {
            trust: current.trust === "verified" ? undefined : "verified",
          })}
          prefetch={false}
          aria-current={current.trust === "verified" ? "page" : undefined}
          className={chipClass(current.trust === "verified")}
        >
          {labels.verifiedOnly}
        </Link>
      </div>

      {/* A plain GET form: submits without JS, and the URL stays the state. */}
      <form action={base} method="get" className="mt-3 flex flex-wrap gap-2">
        {current.gov ? <input type="hidden" name="gov" value={current.gov} /> : null}
        {current.trust ? (
          <input type="hidden" name="trust" value={current.trust} />
        ) : null}
        <label className="sr-only" htmlFor="college-q">
          {labels.searchLabel}
        </label>
        <input
          id="college-q"
          name="q"
          type="search"
          defaultValue={current.q ?? ""}
          maxLength={64}
          placeholder={labels.searchPlaceholder}
          className="tap-target min-w-0 flex-1 rounded-pill border border-cream-line bg-card px-3.5 text-[13px] text-ink"
        />
        <button
          type="submit"
          className="tap-target inline-flex items-center rounded-pill border border-brand bg-brand px-4 text-[12.5px] font-semibold text-white"
        >
          {labels.searchSubmit}
        </button>
      </form>
    </>
  );
}
