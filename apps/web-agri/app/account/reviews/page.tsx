import { Card, EmptyState } from "@agri/ui";
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import Link from "next/link";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";
import { fetchMyReviews, pickBody, statusTone, type MyReview } from "@/lib/account-reviews";

/**
 * /account/reviews — what you wrote (AG-U5 P4).
 *
 * The mirror image of the console's `/business/reviews`, which shows what was
 * written ABOUT a business you own. This one is your own words, wherever you
 * left them.
 *
 * It exists because a review is `pending` on write and therefore absent from
 * every public list, so "where did my review go?" had no answer anywhere on
 * the platform. `GET /reviews/mine` was added for this page.
 */
export const metadata: Metadata = { title: "My reviews", robots: { index: false } };

export const dynamic = "force-dynamic";

export default async function MyReviewsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/account/reviews");
  const token = await auth.getAccessToken();

  const [t, locale, reviews] = await Promise.all([
    getTranslations("ui.account"),
    getLocale(),
    token ? fetchMyReviews(token) : Promise.resolve(null),
  ]);

  return (
    <main className="pb-6">
      <h1 className="font-display text-[21px] font-extrabold leading-tight text-ink">
        {t("reviewsPage.title")}
      </h1>
      <p className="mb-4 mt-1 text-[13px] text-sub">{t("reviewsPage.sub")}</p>

      {reviews === null ? (
        // NOT the empty state. Telling someone who has written reviews that
        // they have not is both false and exactly the fear this page exists
        // to answer.
        <p
          role="alert"
          className="rounded-card border border-alert-line bg-alert-bg px-3.5 py-3 text-[13px] text-ink"
        >
          {t("prefs.loadFailed")}
        </p>
      ) : reviews.length === 0 ? (
        <EmptyState
          icon="⭐"
          title={t("reviewsPage.empty")}
          action={
            <Link
              href="/directory"
              prefetch={false}
              className="tap-target inline-flex w-full items-center justify-center rounded-pill bg-brand px-4 py-2 text-[13px] font-semibold text-white no-underline"
            >
              {t("reviewsPage.emptyCta")}
            </Link>
          }
          className="border-cream-line bg-cream"
        />
      ) : (
        <ul className="space-y-2.5">
          {reviews.map((review) => (
            <ReviewRow key={review.id} review={review} locale={locale} t={t} />
          ))}
        </ul>
      )}
    </main>
  );
}

function ReviewRow({
  review,
  locale,
  t,
}: {
  review: MyReview;
  locale: string;
  t: (key: string, values?: Record<string, string | number>) => string;
}) {
  const tone = statusTone(review.moderation_status);
  const body = pickBody(review.body, locale);
  // A target that no longer resolves still shows the review — a vanished
  // listing must not take your words with it.
  const name = review.target_name ?? t("reviewsPage.unknownTarget");
  const href = !review.target_slug
    ? null
    : review.target_type === "product"
      ? `/catalog/${review.target_slug}`
      : `/directory/businesses/${review.target_slug}`;

  return (
    <li>
      <Card className="p-3.5">
        <div className="flex flex-wrap items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="truncate font-display text-[14px] font-extrabold text-ink">
              {href ? (
                <Link href={href} prefetch={false} className="text-ink no-underline">
                  {name}
                </Link>
              ) : (
                name
              )}
            </p>
            <p className="mt-0.5 text-[13px] text-accent">
              <span className="sr-only">
                {t("reviewsPage.ratingLabel", { rating: review.rating })}
              </span>
              <span aria-hidden="true">
                {"★".repeat(review.rating) + "☆".repeat(5 - review.rating)}
              </span>
            </p>
          </div>
          <span
            className={`inline-flex shrink-0 items-center rounded-pill px-2.5 py-1 text-[11px] font-extrabold ${tone.className}`}
          >
            {t(`reviewsPage.${tone.key}`)}
          </span>
        </div>
        {body ? <p className="mt-2 text-[13px] leading-relaxed text-sub">{body}</p> : null}
        {tone.key === "pending" ? (
          <p className="mt-2 text-[11.5px] text-muted">{t("reviewsPage.pendingNote")}</p>
        ) : null}
        {tone.key === "rejected" ? (
          <p className="mt-2 text-[11.5px] text-muted">{t("reviewsPage.rejectedNote")}</p>
        ) : null}
      </Card>
    </li>
  );
}
