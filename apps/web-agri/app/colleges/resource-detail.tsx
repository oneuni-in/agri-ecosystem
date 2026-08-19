import { Eyebrow, Wrap } from "@agri/ui";
import Link from "next/link";

import type { ResourceDetail } from "@/lib/education";

/**
 * The shared body of `/scholarships/[slug]` and `/exams/[slug]`.
 *
 * One component because the two are the same shape -- spec §4 puts them in one
 * table for exactly that reason. The routes stay separate because they rank
 * for different queries.
 */
export function ResourceDetailBody({
  resource,
  labels,
}: {
  resource: ResourceDetail;
  labels: {
    crumbHome: string;
    crumb: string;
    crumbHref: string;
    eyebrow: string;
    provider: string;
    eligibility: string;
    benefit: string;
    opens: string;
    closes: string;
    session: string;
    checked: string;
    officialLink: string;
    levels: Record<string, string>;
  };
}) {
  const win = (resource.window ?? {}) as {
    opens?: string;
    closes?: string;
    session?: string;
  };

  return (
    <main className="bg-cream pb-10">
      <Wrap>
        <nav className="mt-3.5 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted">
          <Link href="/" prefetch={false} className="tap-target text-brand no-underline">
            {labels.crumbHome}
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <Link
            href={labels.crumbHref}
            prefetch={false}
            className="tap-target text-brand no-underline"
          >
            {labels.crumb}
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{resource.name.en ?? resource.slug}</span>
        </nav>

        <Eyebrow className="mt-3">{labels.eyebrow}</Eyebrow>
        <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-extrabold text-ink">
          {resource.name.en ?? resource.slug}
        </h1>

        {resource.levels.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {resource.levels.map((level) => (
              <span
                key={level}
                className="rounded-pill bg-brand-soft px-2 py-0.5 text-[10px] font-semibold text-brand-deep"
              >
                {labels.levels[level] ?? level}
              </span>
            ))}
          </div>
        ) : null}

        {resource.provider ? (
          <p className="mt-3 text-[13px] text-ink">
            <span className="text-muted">{labels.provider} </span>
            {resource.provider}
          </p>
        ) : null}

        {resource.benefit ? (
          <section className="mt-5">
            <h2 className="font-display text-[16px] font-extrabold text-ink">{labels.benefit}</h2>
            <p className="mt-1 max-w-[70ch] text-[13px] leading-[1.6] text-ink">
              {resource.benefit}
            </p>
          </section>
        ) : null}

        {resource.eligibility.en ? (
          <section className="mt-5">
            <h2 className="font-display text-[16px] font-extrabold text-ink">
              {labels.eligibility}
            </h2>
            <p className="mt-1 max-w-[70ch] text-[13px] leading-[1.6] text-ink">
              {resource.eligibility.en}
            </p>
          </section>
        ) : null}

        {win.opens ?? win.closes ?? win.session ? (
          <dl className="mt-5 flex flex-wrap gap-x-6 gap-y-1 text-[13px]">
            {win.session ? (
              <div>
                <dt className="inline text-muted">{labels.session} </dt>
                <dd className="inline font-semibold text-ink">{win.session}</dd>
              </div>
            ) : null}
            {win.opens ? (
              <div>
                <dt className="inline text-muted">{labels.opens} </dt>
                <dd className="inline font-semibold text-ink">{win.opens}</dd>
              </div>
            ) : null}
            {win.closes ? (
              <div>
                <dt className="inline text-muted">{labels.closes} </dt>
                <dd className="inline font-semibold text-ink">{win.closes}</dd>
              </div>
            ) : null}
          </dl>
        ) : null}

        {/* The stamp is prominent, not a footnote: an application window that
            has quietly gone stale is the failure mode that costs a student a
            year. */}
        <p className="mt-6 text-[12px] text-muted">
          {labels.checked} {resource.last_verified_at}
        </p>

        <p className="mt-3">
          <a
            href={resource.official_url}
            rel="nofollow noopener"
            className="tap-target inline-flex items-center rounded-pill border border-brand bg-brand px-4 text-[12.5px] font-semibold text-white no-underline"
          >
            {labels.officialLink}
          </a>
        </p>
      </Wrap>
    </main>
  );
}
