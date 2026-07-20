import { Card, RatingStars } from "@agri/ui";

type LocalizedText = Record<string, string>;

export type RatingSummary = { rating_avg: string | null; rating_count: number };
export type ReviewItem = {
  id: string;
  rating: number;
  body: LocalizedText | null;
  created_at: string;
};

/**
 * Server component — reviews are fetched in `page.tsx` alongside `fetchDetail`
 * (public backend reads, `next: { revalidate: 300 }`), never through the
 * `/api/reviews` proxy: that proxy is auth-required by design (Task 10) and
 * would 401 for guests browsing the page.
 */
export function ReviewsSection({
  summary,
  items,
}: {
  summary: RatingSummary;
  items: ReviewItem[];
}) {
  return (
    <section className="mt-6 space-y-2.5" aria-labelledby="reviews-h">
      <h2 id="reviews-h" className="font-display text-[16px] font-extrabold text-ink">
        Reviews
        {summary.rating_count > 0 ? (
          <>
            {" "}
            · <RatingStars value={summary.rating_avg ?? ""} /> ({summary.rating_count})
          </>
        ) : null}
      </h2>
      {items.length === 0 ? (
        <p className="text-[13px] text-sub">No reviews yet.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((review) => (
            <li key={review.id}>
              <Card className="space-y-1.5 p-3">
                <RatingStars value={review.rating} />
                {review.body?.en ? (
                  <p className="text-[13.5px] text-ink">{review.body.en}</p>
                ) : null}
              </Card>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
