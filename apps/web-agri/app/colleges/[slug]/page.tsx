import { Eyebrow, Wrap } from "@agri/ui";
import {
  breadcrumbJsonLd,
  buildMetadata,
  canonicalUrl,
  collegeJsonLd,
  JsonLd,
} from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";

import { fetchInstitution, type InstitutionDetail } from "@/lib/education";

/**
 * Phase 2 — `/colleges/[slug]`, the page the trust model exists for.
 *
 * EVERY DATA DECISION READS `can_show_admission_data`, the server-computed
 * boolean. Exactly two things read `trust`/`status` directly: the badge, which
 * is rendering the trust itself, and the noindex/JSON-LD decision, which is
 * about indexability rather than about what data to show. Nothing re-derives
 * the rule — it lives in one place on the server and a second copy would
 * disagree with it eventually.
 *
 * THREE OUTCOMES FROM THE FETCH, not two. `null` is "the API says this slug
 * does not exist" → a real 404. `"unavailable"` is "we could not ask" → a
 * degraded page, never a 404: turning an incident into a hard 404 tells Google
 * a college that exists is gone, and that is slow and expensive to undo.
 */
export const revalidate = 3600;

function indexable(college: InstitutionDetail): boolean {
  return college.trust === "verified" && college.status === "active";
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const [t, { slug }] = await Promise.all([getTranslations("ui.colleges"), params]);
  const college = await fetchInstitution(slug);

  if (college === null || college === "unavailable") {
    return buildMetadata({
      title: t("metaTitle"),
      canonical: canonicalUrl("https://agri.in", "/colleges"),
      siteName: "Agri.in",
      noIndex: true,
    });
  }

  return buildMetadata({
    title: college.name,
    description: t("detailMetaDescription", {
      name: college.name,
      place: college.state ?? "India",
    }),
    canonical: canonicalUrl("https://agri.in", `/colleges/${college.slug}`),
    siteName: "Agri.in",
    // A `listed` row was never checked against the institution's own page, and
    // a closed one must not be advertised. Neither belongs in an index.
    noIndex: !indexable(college),
  });
}

function Stamp({ label, url, on }: { label: string; url: string | null; on: string }) {
  const host = url ? new URL(url).hostname.replace(/^www\./, "") : null;
  return (
    <span>
      {label}
      {host ? (
        <>
          {" · "}
          <a href={url ?? "#"} rel="nofollow noopener" className="text-brand no-underline">
            {host}
          </a>
        </>
      ) : null}
      {" · "}
      {on}
    </span>
  );
}

export default async function CollegePage({ params }: { params: Promise<{ slug: string }> }) {
  const [t, { slug }] = await Promise.all([getTranslations("ui.colleges"), params]);
  const college = await fetchInstitution(slug);

  // "We could not ask" is not "it does not exist". Render the degraded state
  // rather than a 404 -- an incident must not de-index a real college.
  if (college === "unavailable") {
    return (
      <main className="bg-cream pb-10">
        <Wrap>
          <div className="mt-8 rounded-card border border-cream-line bg-card p-5">
            <p className="text-[13.5px] font-semibold text-ink">{t("unavailableTitle")}</p>
            <p className="mt-1 text-[12.5px] text-muted">{t("unavailableBody")}</p>
            <Link
              href="/colleges"
              prefetch={false}
              className="tap-target mt-3 inline-flex items-center rounded-pill border border-brand bg-brand px-4 text-[12.5px] font-semibold text-white no-underline"
            >
              {t("backToColleges")}
            </Link>
          </div>
        </Wrap>
      </main>
    );
  }

  if (college === null) notFound();

  // Incoming links to renamed institutions are exactly the traffic worth
  // keeping. The API deliberately did NOT redirect -- it handed us the
  // pointer, and issuing the 301 is this page's job.
  if (college.status === "merged" && college.merged_into_slug) {
    permanentRedirect(`/colleges/${college.merged_into_slug}`);
  }

  const full = college.can_show_admission_data;
  const closed = college.status === "closed" || college.status === "merged";
  const place = [college.district, college.state].filter(Boolean).join(", ");

  return (
    <main className="bg-cream pb-10">
      <Wrap>
        <nav className="mt-3.5 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted">
          <Link href="/" prefetch={false} className="tap-target text-brand no-underline">
            {t("crumbHome")}
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <Link href="/colleges" prefetch={false} className="tap-target text-brand no-underline">
            {t("crumb")}
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{college.name}</span>
        </nav>

        {/* A merged row with NO successor is a data bug, not a redirect. It
            renders like a closed one rather than sending anyone to
            /colleges/null. */}
        {closed ? (
          <div className="mt-4 rounded-card border border-danger bg-danger-soft p-4">
            <p className="text-[13.5px] font-extrabold text-danger-fg">{t("closedTitle")}</p>
            <p className="mt-1 text-[12.5px] text-danger-fg">{t("closedBody")}</p>
          </div>
        ) : null}

        {!full && !closed ? (
          <div className="mt-4 rounded-card border border-cream-line bg-card p-4">
            <p className="text-[13.5px] font-extrabold text-ink">{t("listedTitle")}</p>
            <p className="mt-1 text-[12.5px] text-muted">{t("listedBody")}</p>
          </div>
        ) : null}

        <Eyebrow className="mt-4">{t("eyebrow")}</Eyebrow>
        <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-extrabold text-ink">
          {college.name}
        </h1>
        <p className="mt-1 text-[13px] text-muted">
          {t(`kinds.${college.kind}`)}
          {place ? ` · ${place}` : ""}
          {college.established_year ? ` · ${t("established")} ${college.established_year}` : ""}
        </p>

        <p className="mt-2 text-[11.5px] text-muted">
          <Stamp
            label={full ? t("verifiedStamp") : t("listedStamp")}
            url={college.source_url}
            on={college.last_verified_at}
          />
        </p>

        {college.parent ? (
          <p className="mt-2 text-[12.5px] text-muted">
            {t("partOf")}{" "}
            <Link
              href={`/colleges/${college.parent.slug}`}
              prefetch={false}
              className="text-brand no-underline"
            >
              {college.parent.name}
            </Link>
          </p>
        ) : null}

        {/* Programmes are listed for a `listed` college too, minus the
            numbers. "This college runs B.Sc. Agriculture" is true and useful;
            what it costs is a claim nobody checked. Dropping the programme
            entirely would discard a true fact to avoid an untrue one. */}
        {college.programmes.length > 0 ? (
          <section className="mt-6">
            <h2 className="font-display text-[17px] font-extrabold text-ink">
              {t("programmesTitle")}
            </h2>
            <div className="mt-3 grid gap-3">
              {college.programmes.map((offering) => (
                <article
                  key={offering.programme_slug}
                  className="rounded-card border border-cream-line bg-card p-4"
                >
                  <h3 className="text-[14.5px] font-extrabold text-ink">
                    {offering.name.en ?? offering.programme_slug}
                  </h3>
                  <p className="mt-1 text-[12px] text-muted">
                    {t(`levels.${offering.level}`)}
                    {offering.duration_months
                      ? ` · ${t("months", { count: offering.duration_months })}`
                      : ""}
                  </p>

                  {full ? (
                    <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[12.5px]">
                      {offering.intake_seats !== null ? (
                        <div>
                          <dt className="inline text-muted">{t("seats")} </dt>
                          <dd className="inline font-semibold text-ink">
                            {offering.intake_seats}
                          </dd>
                        </div>
                      ) : null}
                      {offering.annual_fees_inr !== null ? (
                        <div>
                          <dt className="inline text-muted">{t("annualFees")} </dt>
                          <dd className="inline font-semibold text-ink">
                            ₹{offering.annual_fees_inr.toLocaleString("en-IN")}
                          </dd>
                        </div>
                      ) : null}
                      {offering.admission_route ? (
                        <div>
                          <dt className="inline text-muted">{t("admissionRoute")} </dt>
                          <dd className="inline font-semibold text-ink">
                            {offering.admission_route}
                          </dd>
                        </div>
                      ) : null}
                    </dl>
                  ) : null}

                  {/* The OFFERING's own stamp, separate from the college's.
                      That split is the whole reason institution_programmes
                      carries its own source_url and last_verified_at: one
                      stamp would put a two-year-old fee under a fresh badge. */}
                  {full && offering.last_verified_at ? (
                    <p className="mt-2 text-[11px] text-muted">
                      <Stamp
                        label={t("feesStamp")}
                        url={offering.source_url}
                        on={offering.last_verified_at}
                      />
                    </p>
                  ) : null}
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {college.constituents.length > 0 ? (
          <section className="mt-6">
            <h2 className="font-display text-[17px] font-extrabold text-ink">
              {t("constituentsTitle")}
            </h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {college.constituents.map((child) => (
                <Link
                  key={child.slug}
                  href={`/colleges/${child.slug}`}
                  prefetch={false}
                  className="tap-target inline-flex items-center rounded-pill border border-cream-line bg-card px-3.5 text-[12.5px] font-semibold text-ink no-underline"
                >
                  {child.name}
                </Link>
              ))}
            </div>
          </section>
        ) : null}

        {college.website && !closed ? (
          <p className="mt-6">
            <a
              href={college.website}
              rel="nofollow noopener"
              className="tap-target inline-flex items-center rounded-pill border border-brand bg-brand px-4 text-[12.5px] font-semibold text-white no-underline"
            >
              {t("officialSite")}
            </a>
          </p>
        ) : null}
      </Wrap>

      {/* Verified and active only. Marking up an unchecked bulk-directory row
          as a CollegeOrUniversity with an address nobody confirmed is the kind
          of claim that earns a manual action. */}
      {indexable(college) ? (
        <>
          <JsonLd
            data={collegeJsonLd({
              name: college.name,
              url: `https://agri.in/colleges/${college.slug}`,
              ...(college.contact_phone ? { telephone: college.contact_phone } : {}),
              ...(college.contact_email ? { email: college.contact_email } : {}),
              ...(college.website ? { website: college.website } : {}),
              ...(college.established_year
                ? { foundingDate: String(college.established_year) }
                : {}),
              address: {
                ...(college.address ? { streetAddress: college.address } : {}),
                ...(college.district ? { locality: college.district } : {}),
                ...(college.state ? { region: college.state } : {}),
                ...(college.pincode ? { postalCode: college.pincode } : {}),
              },
              ...(college.lat && college.lng
                ? { geo: { latitude: Number(college.lat), longitude: Number(college.lng) } }
                : {}),
            })}
          />
          <JsonLd
            data={breadcrumbJsonLd([
              { name: t("crumbHome"), url: "https://agri.in/" },
              { name: t("crumb"), url: "https://agri.in/colleges" },
              { name: college.name, url: `https://agri.in/colleges/${college.slug}` },
            ])}
          />
        </>
      ) : null}
    </main>
  );
}
