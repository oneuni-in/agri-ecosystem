# A-U3 — Content, helplines, directory, ads activation (FINAL v1)

**Schedule slot: days 45–47 + 50 of blueprint v7.** Plan: `docs/Sprint/agri_final_plan.md`.
**Git context:** A-U1 and A-U2 are complete on this branch, unmerged (CI minutes; self-hosted
runners in progress). A-U3 CONTINUES ON THE SAME BRANCH and PR #34. Prefix commits `a-u3:`.
**Do NOT push until the owner says so** — commit locally only.

**Read before writing code:** this prompt · `docs/qa/agri-acceptance-checklist.md` (current
state) · `docs/ads/vertical-onboarding.md` · `backend/core/modules/content/CLAUDE.md` and
`market_data/CLAUDE.md` · `docs/Sprint/agri_final_plan.md` A-U3 section.

---

## 0 · Carry-over: close the four open A-U1 rows inside this pass

`docs/qa/agri-acceptance-checklist.md` has four A-U1 rows still unverified. Open the file,
identify them, and close each one **inside the workstream that touches it** — do not schedule
a separate pass. Known overlaps:

- **AG-A5 (search band → results)** → close during W3 (hub directory/search surfaces).
- **AG-A6 (directory row real data)** → close during W3, with the real seeded businesses.
- The other two: close where they naturally land; if one has no home in A-U3's scope, say so
  explicitly at CP3 with a proposed slot rather than silently leaving it open.

Every closed row gets its verification method recorded, same as the rest.

Also settle the **A-U1 helplines deviation**: helplines shipped as a static TS file pending
E5 migration. W2 below is where that debt is paid — after migration, the static file is
deleted, not left as a dead fallback.

---

## 1 · Workstreams

### W1 · News + video content type (D45) — `content` module (E6)
- RSS ingest worker: curated source list (config, not hardcoded), attribution preserved
  (source name + link + published-at), state/vertical tags, dedupe on canonical URL.
  Editorial curation state — nothing auto-publishes; `pending` is the default (module rule).
- **Video as a first-class content kind:** `kind: video` with `duration` and `language`
  fields; embeds from approved providers only (no arbitrary iframe HTML). The home knowledge
  row and the knowledge hub render video cards with the play/duration treatment from the A1
  reference.
- Feed UI + bookmarks on `web-agri`; content surfaces localised EN/TA/HI.
- Honesty rule holds: empty module → section absent. No lorem, no placeholder articles.

### W2 · Knowledge CMS, advisories, helplines → E5 (D46–47)
- Knowledge CMS with the Claude-assist + **human gate** flow (draft → human approval →
  publish), i18n fields; guides render with FAQPage JSON-LD where they're Q&A shaped.
- **Pest-alert advisory content type** — human-written only. Seasonal/regional targeting
  fields so an advisory surfaces for the right district and window. No AI-authored advisory
  text ships without human sign-off (the dosage/scheme/loan rule extends here).
- Livestock/poultry care pack seeds (EN/TA/HI) — content, not directory.
- **Helplines → E5 dataset:** migrate `apps/web-agri/data/helplines.ts` into the market_data
  (E5) dataset shape with `source` + `verified_on` per number; verify each number against its
  official source as part of the migration; delete the static file; offline click-to-call page
  (D59 scope) serves from the dataset and stays cached in the service worker.
- **Schemes static v0:** the scheme entries behind the home spotlight become real E5 rows
  with `verified_against` + `verified_on`, plus a `/schemes` listing. Eligibility wizard is
  Stage C — NOT this pass.

### W3 · Hub directory + search surfaces (D47) — closes AG-A5/AG-A6
- Hub directory UI: browse/filter agri businesses by category × pincode, using the existing
  E1 directory engine; sponsored pins only where a real campaign exists, always labelled.
- Search results surface for the home search band's federated queries — the band already
  posts; this pass gives the results page its real home (reuse the `/search` facade; no new
  search engine).
- Close AG-A5 (band → results round-trip) and AG-A6 (directory row shows real seeded data)
  with recorded verification.

### W4 · Ads activation — CONFIG ONLY (D50)
- Agri slot entries + rate-card rows + house creatives per `docs/ads/vertical-onboarding.md`.
- **Zero ads engine code.** If the recipe doesn't suffice, STOP and escalate — that's a defect
  in the recipe (and a crack in the M6 portability proof), not something to patch around.
  Note: A-U1 touched `ads/service.py`; if that change is still in the diff and still
  unjustified, resolve it in this pass — either justify it in the PR body or revert it.
- Verify cross-vertical advertiser analytics still read correctly with agri campaigns present.
- Frequency caps and "Sponsored" labelling verified on every agri surface that serves an ad.

---

## 2 · Acceptance checklist additions (append; never rewrite)
AG-A22 news items show real source + attribution, nothing auto-published · AG-A23 video
content renders with duration/language and an approved-provider embed · AG-A24 knowledge
publish requires the human gate (attempt publish as non-approver → rejected) · AG-A25 pest
advisory surfaces only in its target district/window · AG-A26 helplines served from E5 with
per-number source + verified_on; static file gone; offline page works with network off ·
AG-A27 schemes list renders verified stamps from data · AG-A28 hub directory filters return
real businesses; sponsored pins labelled · AG-A29 agri ads serve via config only with caps +
labels · AG-A30 Lighthouse ≥ 0.90 holds on `/`, `/categories`, `/tools`, and the new
content/directory routes.

## 3 · Checkpoints (in-session reviews — NO pushes)
- **CP1:** news ingest + video kind + feed UI; show me real curated items with attribution.
- **CP2:** knowledge CMS + human gate + pest advisory + helplines E5 migration (static file
  deleted) + schemes v0.
- **CP3:** hub directory + search results (AG-A5/A6 closed) + ads activation by config +
  all checklist rows + screenshots (4 widths, EN/TA/HI on one content page and the directory)
  + the four A-U1 carry-over rows resolved or explicitly slotted. Then STOP.

## 4 · Out of bounds — with reasoning
- **AI assistant (chat, RAG, tools):** A-U4 with its own safety gate; shipping any assistant
  behavior here bypasses a deliberate human sign-off.
- **Ads engine code:** §W4 — M6's proof is the asset being protected.
- **Coins full activation, notifications centre, federated-search polish, PWA sweep:** A-U4.
- **Schemes eligibility wizard, booking engine, loans/insurance routing:** Stage C.
- **Forum / Q&A / events modules:** Stage D — the home Q&A and events cards stay Soon cards.
- **Milk.in / TheOrganic.in / web-id / web-admin:** parked; file issues.
- **Scraping:** APIs and licensed feeds only; respect robots and terms on RSS sources.
- **Auto-publishing anything:** every content path ends at a human approval.

## 5 · Done means
Three checkpoints reviewed · the four A-U1 carry-over rows closed (or explicitly slotted with
a reason) · helplines debt paid and the static file deleted · ads activated with zero engine
edits and the A-U1 `ads/service.py` question resolved · AG-A22…A30 filled with verification
method · binding proofs appended to polish-a1.md · commits prefixed `a-u3:` sitting locally,
ready for the owner's single push to PR #34.
