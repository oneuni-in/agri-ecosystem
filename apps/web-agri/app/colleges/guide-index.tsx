import { Eyebrow, Wrap } from "@agri/ui";
import Link from "next/link";

import type { GuideCard } from "@/lib/education";

/**
 * The shared body of `/counselling` and `/study-abroad`.
 *
 * Both are the same read with a different `kind`, so they share a component
 * and keep separate routes — they rank for different queries and the spec
 * lists them separately.
 */
export function GuideIndexBody({
  guides,
  labels,
}: {
  guides: GuideCard[];
  labels: {
    crumbHome: string;
    crumb: string;
    eyebrow: string;
    title: string;
    sub: string;
    checked: string;
  };
}) {
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
          <span>{labels.crumb}</span>
        </nav>

        <Eyebrow className="mt-3">{labels.eyebrow}</Eyebrow>
        <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-extrabold text-ink">
          {labels.title}
        </h1>
        <p className="mt-1 max-w-[70ch] text-[13px] text-muted">{labels.sub}</p>

        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {guides.map((guide) => (
            <article
              key={guide.slug}
              className="flex flex-col rounded-card border border-cream-line bg-card p-4"
            >
              {guide.state ?? guide.country_code ? (
                <div className="mb-1.5">
                  <span className="rounded-pill bg-accent-soft px-2 py-0.5 text-[10px] font-semibold text-coins-fg">
                    {guide.state ?? guide.country_code}
                  </span>
                </div>
              ) : null}

              <h2 className="text-[15.5px] font-extrabold leading-[1.3] text-ink">
                <Link
                  href={`/guides/${guide.slug}`}
                  prefetch={false}
                  className="text-ink no-underline"
                >
                  {guide.title.en ?? guide.slug}
                </Link>
              </h2>

              {guide.summary.en ? (
                <p className="mt-2 text-[12.5px] leading-[1.5] text-ink">{guide.summary.en}</p>
              ) : null}

              {/* Counselling dates going stale and misleading is a named risk
                  in spec §12, and this stamp is the whole mitigation. It sits
                  on the card, not in a footer. */}
              <p className="mt-2 text-[11px] text-muted">
                {labels.checked} {guide.last_verified_at}
              </p>
            </article>
          ))}
        </div>
      </Wrap>
    </main>
  );
}
