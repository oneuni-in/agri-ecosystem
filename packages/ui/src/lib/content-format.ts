/**
 * A-U3 — pure formatting/extraction helpers for the content surfaces.
 *
 * Here rather than in `apps/web-agri/lib` for the reason the agri
 * calculators are here: `web-agri` has no test runner, and these three
 * are exactly the kind of logic that goes wrong quietly. Presentation
 * only — no fetching, no data shapes beyond what a caller passes in.
 */

/**
 * Pull Q&A pairs out of a guide body, for FAQPage JSON-LD.
 *
 * The A-U3 W2 brief says guides get FAQPage "where they're Q&A shaped",
 * and the load-bearing word is WHERE. Emitting FAQPage over ordinary
 * prose is structured-data spam: it tells a search engine the page
 * answers questions it does not answer, and that is a penalised
 * behaviour, not a clever one.
 *
 * So detection is strict and biased towards returning nothing:
 *  - a question is a line that ENDS in "?" (Tamil and Hindi both use the
 *    ASCII question mark, so one rule covers all three locales);
 *  - it only counts if non-empty, non-question text follows it;
 *  - fewer than two complete pairs → no markup at all.
 *
 * A real FAQ trips this. A guide with one rhetorical question does not.
 */
export function extractFaq(
  body: string,
): { question: string; answer: string }[] {
  const lines = body
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  const pairs: { question: string; answer: string }[] = [];
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]!;
    if (!line.endsWith("?")) continue;
    const answer: string[] = [];
    for (let j = i + 1; j < lines.length && !lines[j]!.endsWith("?"); j += 1) {
      answer.push(lines[j]!);
    }
    if (answer.length) pairs.push({ question: line, answer: answer.join(" ") });
  }
  // Two is the floor: one Q&A is a sentence, not a FAQ.
  return pairs.length >= 2 ? pairs : [];
}

/** `412` → `6:52`. Null in, null out: no duration means no pill, never
 * an invented time (duration is curator-entered — no keyless official
 * API reports it). */
export function formatDuration(seconds: number | null): string | null {
  if (!seconds || seconds < 1) return null;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  const mm = hours ? String(minutes).padStart(2, "0") : String(minutes);
  return `${hours ? `${hours}:` : ""}${mm}:${String(secs).padStart(2, "0")}`;
}

/**
 * The helpline band's footer stamp: distinct sources, and the OLDEST
 * verification date among the numbers shown.
 *
 * Oldest, not newest, deliberately. The stamp is a claim about the whole
 * band, so the honest claim is its weakest member — showing the most
 * recent date would let one freshly-checked number vouch for three that
 * nobody has looked at in years.
 */
export function helplineStamp(
  helplines: readonly { source: string; verified_on: string }[],
): { sources: string; date: string } {
  const sources = [...new Set(helplines.map((h) => h.source))].join(" · ");
  // ISO dates sort lexicographically, so this is a plain min.
  const date = [...helplines.map((h) => h.verified_on)].sort()[0] ?? "";
  return { sources, date };
}
