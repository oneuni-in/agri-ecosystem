"use client";

import { useRef, useState } from "react";

/**
 * A-U4 W1 — the Ask-AI chat island.
 *
 * Deliberately small. The interesting decisions are on the server, and the
 * ones that survive into this file are about honesty:
 *
 * - **Citations render from the API's own list**, never parsed out of the
 *   answer text. The backend assembles them from the retrieved rows'
 *   metadata, so what is shown here is provenance, not something the model
 *   asserted about itself.
 * - **A refusal is not an error.** When the assistant declines a dosage or
 *   eligibility question it returns a route to the verified surface, and
 *   that route is rendered as the primary action. The most useful thing the
 *   assistant can do with a question it must not answer is hand the visitor
 *   to something that can.
 * - **The disclaimers are always on screen**, not behind a tooltip and not
 *   shown once at the start. They are load-bearing copy per the A1
 *   reference, so they sit under the composer where they cannot scroll away.
 */

export interface Citation {
  title: string;
  slug: string;
  source_name: string;
  kind: string;
}

interface Turn {
  id: string;
  question: string;
  answer: string | null;
  citations: Citation[];
  refused: boolean;
  route: string | null;
  failed: boolean;
}

export interface AskCopy {
  placeholder: string;
  send: string;
  sending: string;
  sourcesLabel: string;
  disclaimer: string;
  reviewNote: string;
  errorTitle: string;
  routeCta: string;
  emptyState: string;
  loginNeeded: string;
}

export function AskChat({ copy }: { copy: AskCopy }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  // Held for the life of the tab so the backend's per-conversation turn cap
  // counts a real conversation. It is intentionally NOT persisted: a new tab
  // is a new conversation, and the daily per-user cap is the abuse guard.
  const conversationId = useRef<string | null>(null);
  const listEnd = useRef<HTMLDivElement>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const question = value.trim();
    if (!question || busy) return;

    const id = `${Date.now()}`;
    setTurns((prev) => [
      ...prev,
      { id, question, answer: null, citations: [], refused: false, route: null, failed: false },
    ]);
    setValue("");
    setBusy(true);

    try {
      const res = await fetch("/api/ai/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          question,
          conversation_id: conversationId.current,
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const body = await res.json();
      conversationId.current = body.conversation_id ?? conversationId.current;
      setTurns((prev) =>
        prev.map((turn) =>
          turn.id === id
            ? {
                ...turn,
                answer: body.answer ?? "",
                citations: body.citations ?? [],
                refused: Boolean(body.refused),
                route: body.route ?? null,
              }
            : turn,
        ),
      );
    } catch {
      setTurns((prev) =>
        prev.map((turn) => (turn.id === id ? { ...turn, failed: true } : turn)),
      );
    } finally {
      setBusy(false);
      listEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }

  return (
    <div className="mt-4">
      <div
        aria-live="polite"
        aria-busy={busy}
        className="flex flex-col gap-4"
      >
        {turns.length === 0 ? (
          <p className="rounded-card border border-cream-line bg-card px-4 py-6 text-center text-[13px] text-muted">
            {copy.emptyState}
          </p>
        ) : null}

        {turns.map((turn) => (
          <div key={turn.id} className="flex flex-col gap-2">
            <p className="self-end rounded-card bg-brand-soft px-4 py-2.5 text-[13.5px] font-medium text-brand-deep">
              {turn.question}
            </p>

            {turn.failed ? (
              <p className="rounded-card border border-severe bg-severe-bg px-4 py-3 text-[13px] text-severe-ink">
                {copy.errorTitle}
              </p>
            ) : turn.answer === null ? (
              <p className="px-1 text-[13px] text-muted">{copy.sending}</p>
            ) : (
              <div className="rounded-card border border-cream-line bg-card px-4 py-3.5">
                <p className="whitespace-pre-wrap text-[13.5px] leading-[1.6] text-ink">
                  {turn.answer}
                </p>

                {/* A refusal's route is the primary action — see the file
                    header. Rendered as a link, not a toast, because it is
                    the answer to what the visitor should do next. */}
                {turn.refused && turn.route ? (
                  <a
                    href={turn.route}
                    className="tap-target mt-2.5 inline-flex min-h-[44px] items-center rounded-btn bg-brand px-4 text-[12.5px] font-bold text-white no-underline"
                  >
                    {copy.routeCta}
                  </a>
                ) : null}

                {turn.citations.length > 0 ? (
                  <div className="mt-3 border-t border-cream-line pt-2.5">
                    <b className="block text-[10.5px] font-semibold uppercase tracking-wide text-muted">
                      {copy.sourcesLabel}
                    </b>
                    <ul className="mt-1.5 flex flex-col gap-1">
                      {turn.citations.map((citation, index) => (
                        <li key={`${citation.slug}-${index}`}>
                          <a
                            href={`/knowledge/${citation.slug}`}
                            className="text-[11.5px] font-medium text-brand no-underline"
                          >
                            [{index + 1}] {citation.title}
                          </a>{" "}
                          <span className="text-[10.5px] text-muted">
                            · {citation.source_name}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        ))}
        <div ref={listEnd} />
      </div>

      <form onSubmit={submit} className="mt-4 flex items-center gap-2.5">
        <label htmlFor="ask-input" className="sr-only">
          {copy.placeholder}
        </label>
        <input
          id="ask-input"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder={copy.placeholder}
          maxLength={1000}
          className="min-h-[44px] min-w-0 flex-1 rounded-btn border border-cream-line bg-card px-4 text-[14px] text-ink focus:border-brand focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy || !value.trim()}
          className="inline-flex min-h-[44px] items-center rounded-btn bg-brand px-5 text-[13.5px] font-bold text-white disabled:opacity-50"
        >
          {busy ? copy.sending : copy.send}
        </button>
      </form>

      {/* Load-bearing copy (A1 reference), not decoration: always on screen,
          under the composer, where it cannot scroll out of view. */}
      <p className="mt-2.5 text-[11px] leading-[1.55] text-muted">
        {copy.reviewNote}
      </p>
      <p className="mt-1 text-[11px] font-medium leading-[1.55] text-sub">
        {copy.disclaimer}
      </p>
    </div>
  );
}
