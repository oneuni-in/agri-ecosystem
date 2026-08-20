# "Live on agri.in" activity feed — privacy review

**Scope:** every field the feed can emit, reviewed before the engine ships.
A-U4b O11, owner-approved build 2026-08-20. Flag `agri_live_feed` stays OFF at
★ D57; flipping it is a separate decision that re-reads this document.

## The design stance

Privacy is **by construction, not by filtering**: the `directory.activity`
table has no columns that could hold a person's identity, so a later bug
cannot leak what was never stored. The reference mockup's marquee content
(`agri_home_desktop_v1.html:1146-1149`) is entirely invented — named
businesses tied to exact pincodes, relative times, an unmeasured count — and
is the anti-pattern this review exists to prevent.

Three standing fences, restated:

1. **Consent-first reveals.** A business appears by name only when it is
   already publicly visible (`status='active'`, not soft-deleted — the same
   predicate search indexing uses). An unlisted business never appears, even
   in a "joined" row recorded at its own approval moment.
2. **Coarse location only.** District and state, resolved server-side from a
   need's pincode at write time; the pincode itself is never stored. Where
   the geo tables cannot resolve a district (non-TN pincodes until D65), the
   location is **omitted**, never degraded to the raw pincode.
3. **No fabrication.** Empty window → absent section. No padded lanes, no
   recycled events, no counts that were not measured (the feed emits no
   counts at all), no timestamps rendered into cached HTML (a baked-in
   "2 min ago" lies for the whole cache window).

## Field-by-field verdicts

| Field | Emitted | Why it is safe |
|---|---|---|
| `kind` | yes | one of four fixed enum values; carries nothing about anyone |
| `occurred_at` | on the wire, **not rendered** | needed for the window read; the UI deliberately renders no times (cache honesty); second-level precision over a 24h window does not de-anonymize a district-coarse event |
| `district`, `state` | yes | coarse public geography; NULL when unresolvable — never falls back to pincode |
| `business_name`, `business_slug` | yes, only for publicly-visible businesses | already public on `/directory/businesses/{slug}` and in the search index; the slug links to that same public page |
| `rating` | yes (review rows) | the approved review's star rating is already public on the business page |
| `source_id` | **no** (storage-only) | internal idempotency key (`UNIQUE(kind, source_id)`); never serialized |

## What is deliberately NOT stored (not merely not emitted)

- Any user id (poster, reviewer, claimant, lead sender, owner) — the events'
  bus payloads carry `user_id`/`author_user_id` etc.; the activity writer
  drops them at the transaction boundary.
- The need's pincode or payload text; review body text; inquiry contents.
- `agri_id`, phone fragments, email, locale — present on identity/billing
  bus events, none of which feed this table.
- Admin free-text (claim/verification rejection notes).

## Per-kind review

- **`need_posted`** — "A need was posted in {district}". No poster identity
  of any kind; district resolved and pincode discarded in the same
  transaction. Risk considered: a rural district with one farmer could make
  "a need was posted in X" weakly identifying to neighbours — accepted:
  the same fact is already visible to every covering vendor via the needs
  fan-out, with MORE detail than the feed carries.
- **`business_joined`** — recorded once per business (unique key), only at
  claim/verification approval AND only if publicly visible at that moment.
  The business chose to list publicly; the feed repeats the listing's own
  headline fact.
- **`review_approved`** — name + stars of an approved (already public)
  review's target. The author is invisible. Risk considered: "new review ·
  ★1" could spotlight a fresh negative review; accepted — the review is
  public either way and the feed adds no author information.
- **`lead_sent`** — "A farmer contacted {business}". The sender is
  invisible; timing is not rendered. Risk considered: contact *volume*
  inference about a business — accepted; businesses already display lead
  counts to themselves, and per-event rows without timestamps leak less
  than the reference's fabricated counts would have implied.

## Re-review triggers

Any of these requires re-opening this document before shipping: adding a
field to the wire schema; rendering timestamps; adding a count; a new
`kind`; backfilling historical rows (the feed starts empty on purpose —
only events that happen after the table exists appear).
