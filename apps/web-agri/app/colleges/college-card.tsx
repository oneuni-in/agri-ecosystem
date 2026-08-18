import Link from "next/link";

import type { InstitutionCard } from "@/lib/education";

/**
 * One college in a list.
 *
 * Shows NO fee and NO seat count, ever — not conditionally. A card is where a
 * number is most tempting and least reviewed, and the list API does not send
 * offerings at all, so there is nothing here to leak. The trust badge is the
 * one place in this app allowed to read `trust` directly, because it is
 * rendering the trust itself rather than deciding what data to show; every
 * other decision reads `can_show_admission_data`.
 *
 * The institution NAME is EN-only by design (spec §6): these are proper nouns,
 * and TA/HI carry only where the institution itself publishes them. The chrome
 * around it is translated.
 */
export function CollegeCard({
  college,
  labels,
}: {
  college: InstitutionCard;
  labels: {
    verified: string;
    listed: string;
    government: string;
    private: string;
    established: string;
    kinds: Record<string, string>;
  };
}) {
  const verified = college.trust === "verified";
  const place = [college.district, college.state].filter(Boolean).join(", ");

  return (
    <article className="flex flex-col rounded-card border border-cream-line bg-card p-4">
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
        <span
          className={
            verified
              ? "rounded-pill bg-brand-soft px-2 py-0.5 text-[10px] font-semibold text-brand-deep"
              : "rounded-pill bg-cream px-2 py-0.5 text-[10px] font-semibold text-muted"
          }
        >
          {verified ? labels.verified : labels.listed}
        </span>
        {college.is_government === null ? null : (
          <span className="rounded-pill bg-accent-soft px-2 py-0.5 text-[10px] font-semibold text-coins-fg">
            {college.is_government ? labels.government : labels.private}
          </span>
        )}
      </div>

      <h2 className="text-[15.5px] font-extrabold leading-[1.3] text-ink">
        <Link
          href={`/colleges/${college.slug}`}
          prefetch={false}
          className="text-ink no-underline"
        >
          {college.name}
        </Link>
      </h2>

      <p className="mt-1 text-[12.5px] text-muted">
        {labels.kinds[college.kind] ?? college.kind}
        {place ? ` · ${place}` : ""}
      </p>

      {college.established_year ? (
        <p className="mt-1 text-[11.5px] text-muted">
          {labels.established} {college.established_year}
        </p>
      ) : null}
    </article>
  );
}
