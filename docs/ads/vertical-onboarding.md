# Onboarding a vertical onto the ads engine

**Status: written at A-U3 W4 (2026-08-17), from the two runs that actually
happened.** This file is referenced by `sprint3.5_M1-M6` §M6, by
`agri_final_plan.md` D50 and by the A-U1/A-U3 build prompts, and until now
it did not exist — A-U1 recorded that gap in `polish-a1.md` §0 and worked
from `polish-u1.md` instead. It is written here so the next vertical is
not a third round of rediscovery.

**The claim being protected:** onboarding a vertical is CONFIG, not code.
If you find yourself editing anything under `backend/core/modules/ads/`
other than the `SLOT_KEYS` set, stop — that is a defect in the engine's
portability, and it needs escalating rather than patching around.

---

## What counts as "config"

| Change | File | Why it is config, not engine |
|---|---|---|
| Register the slot | `modules/ads/service.py` → `SLOT_KEYS` | A frozenset of allowed slot names. It is an allowlist, not behaviour: nothing branches on which vertical a slot belongs to. **This is the one file under `modules/ads/` you may touch, and only to add a string.** |
| House creatives | `scripts/seed_house_ads.py` | Per-vertical advertiser + copy + target URLs. |
| Creative size | `scripts/seed_sample_media.py` | The slot's inventory shape. |
| Rate card | usually NOTHING — see below | |
| Serve the slot | the app's `lib/ads.ts` | Frontend, not engine. |

### Why `SLOT_KEYS` is not an engine edit

It is the same call as adding a route to `public_routes.txt`: a
declaration that a name is permitted. The serving path — candidate
selection, weighting, budget consumption, frequency capping, beacons,
moderation — never asks which vertical a slot belongs to. A-U1's
`agri_home_hero_xl` line is one entry in that set, and A-U3 re-checked
the whole diff under `modules/ads/` and found nothing else. If a future
pass finds a real behavioural edit there, THAT is the escalation.

---

## The steps

1. **Register the slot key.** Add the string to `SLOT_KEYS` with a comment
   saying which surface it is and which existing slot it mirrors in size.

2. **Give the vertical its own house advertiser.** Not a shared one. The
   "Sponsored" label must never attach a milk business's name to an
   agri.in page — `seed_house_ads.py` keeps `_AGRI_HOUSE_BUSINESS`
   separate for exactly this reason.

3. **Seed house creatives in all three locales.** A slot with no eligible
   creative renders its house fallback, which is a first-party door and
   carries NO badge and NO beacons — it is not a served ad. That is
   correct, but it means an empty slot looks fine and you will not notice
   the seed never ran. Check `/ads/serve` returns a non-empty `ads`.

4. **Rate card: usually nothing to do.** The card is keyed by pincode
   TIER (1–5), not by vertical, so a new vertical prices correctly the
   moment it exists. `category_multipliers_bp` is the only
   vertical-flavoured field, and a category absent from it prices at 1×
   (`pricing.py`: "a category absent from the card prices at 1x").
   **Do not invent multipliers for a new vertical.** A multiplier is a
   pricing decision an owner makes, not a default an engineer picks; 1× is
   the honest starting point.

5. **Serve it from the app, server-side.** Copy `lib/ads.ts`. The
   important part is forwarding `x-forwarded-for` and `user-agent`: the
   frequency cap hashes the VIEWER, and without forwarding, every SSR
   render hashes to the server and the caps become meaningless.

6. **Verify, in this order.** Each step catches a different failure:
   - `/ads/serve?slot=…` returns a creative (seed ran, campaign active,
     creative approved — creatives default to `pending`);
   - repeated serves from ONE viewer dry up at
     `ads_freq_cap_per_day × creatives` and then return `[]`;
   - the rendered page shows the "★ Sponsored" badge over the creative;
   - `ads.impressions` / `ads.clicks` accumulate rows for the new
     `slot_key` and it appears in `/admin/ads/performance` beside the
     other verticals with no code change.

---

## Traps, both hit for real

**A capped viewer looks like a broken slot.** During A-U3's verification
the home rendered the house fallback with no badge, which read as "the
label is missing". It was the frequency cap firing correctly through the
SSR path — the browser context had already consumed its 6 serves
(2 creatives × cap 3). Re-check with a fresh `userAgent` before
concluding anything is wrong.

**A recreated docker volume silently un-provisions everything.** The
house-ad seed, the Meili index settings and the geo data all live outside
migrations. After `docker compose down -v` you must re-run
`scripts.seed_house_ads`, `ensure_indexes()` and `scripts.load_geo` — a
slot that serves nothing is far more often this than a config mistake.

**`₹` through Windows `curl`/`psql` pipelines renders as `â‚¹`.** The
database bytes are fine (`e282b9`). Check the rendered page, not a
terminal dump, before "fixing" an encoding bug that does not exist.
