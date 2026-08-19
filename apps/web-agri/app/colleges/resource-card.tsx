import Link from "next/link";

import type { ResourceCard as Resource } from "@/lib/education";

/**
 * One scholarship or exam.
 *
 * `official_url` and `last_verified_at` are non-nullable on the wire, so a
 * card literally cannot render without saying where it came from and when it
 * was checked. That is the same rule the E6 content cards carry, and it is the
 * reason those two fields were made required in the API rather than optional.
 */
export function ResourceListCard({
  resource,
  labels,
}: {
  resource: Resource;
  labels: { checked: string; levels: Record<string, string>; opens: string; closes: string };
}) {
  const win = (resource.window ?? {}) as { opens?: string; closes?: string; session?: string };

  return (
    <article className="flex flex-col rounded-card border border-cream-line bg-card p-4">
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
        {resource.levels.map((level) => (
          <span
            key={level}
            className="rounded-pill bg-brand-soft px-2 py-0.5 text-[10px] font-semibold text-brand-deep"
          >
            {labels.levels[level] ?? level}
          </span>
        ))}
      </div>

      <h2 className="text-[15.5px] font-extrabold leading-[1.3] text-ink">
        <Link
          href={`/${resource.kind === "exam" ? "exams" : "scholarships"}/${resource.slug}`}
          prefetch={false}
          className="text-ink no-underline"
        >
          {resource.name.en ?? resource.slug}
        </Link>
      </h2>

      {resource.provider ? (
        <p className="mt-1 text-[12.5px] text-muted">{resource.provider}</p>
      ) : null}

      {resource.benefit ? (
        <p className="mt-2 text-[12.5px] leading-[1.5] text-ink">{resource.benefit}</p>
      ) : null}

      {/* The window renders only when the data has one. An invented "applications
          open soon" is worse than no line at all -- a student plans around it. */}
      {win.opens ?? win.closes ? (
        <p className="mt-2 text-[12px] text-muted">
          {win.opens ? `${labels.opens} ${win.opens}` : null}
          {win.opens && win.closes ? " · " : null}
          {win.closes ? `${labels.closes} ${win.closes}` : null}
        </p>
      ) : null}

      <p className="mt-2 text-[11px] text-muted">
        {labels.checked} {resource.last_verified_at} ·{" "}
        <a href={resource.official_url} rel="nofollow noopener" className="text-brand no-underline">
          {new URL(resource.official_url).hostname.replace(/^www\./, "")}
        </a>
      </p>
    </article>
  );
}
