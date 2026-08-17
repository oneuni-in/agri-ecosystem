"use client";

/**
 * A-U3 W2 — the knowledge CMS.
 *
 * Two halves, deliberately kept apart on screen because they are two
 * different acts with two different permissions behind them:
 *
 *   REVIEW  — the queue. Read what the RSS worker fetched or an editor
 *             drafted, then approve or reject it. Backed by
 *             `content.publish`.
 *   DRAFT   — the composer. Write a guide, an advisory or a curated
 *             video. Backed by `content.write`, and whatever it creates
 *             lands `pending` and comes back through the queue.
 *
 * The UI cannot skip the gate, and not because it politely declines to:
 * there is no API shape that would let it. `ItemIn` has no
 * `moderation_status` field and `create_item()` strips one if it somehow
 * arrives, so "save and publish" is not a button we chose not to build —
 * it is a request the backend has no way to honour.
 *
 * "Claude-assist" here means the drafting help an editor already has in
 * their own tools; this console deliberately ships no generate button.
 * An assistant that writes advisory text straight into a publish queue
 * is exactly the shortcut the human gate exists to prevent, and the AI
 * surfaces are A-U4 with their own safety review.
 */

import { cn, useToast } from "@agri/ui";
import { useCallback, useEffect, useState } from "react";

import { ApiError, getJson, postJson } from "@/lib/api";

const STATUSES = [
  { key: "pending", label: "Pending review" },
  { key: "approved", label: "Published" },
  { key: "rejected", label: "Rejected" },
] as const;

type StatusKey = (typeof STATUSES)[number]["key"];

const KINDS = ["article", "video", "guide", "advisory"] as const;
type Kind = (typeof KINDS)[number];

const LOCALES = ["en", "ta", "hi"] as const;
type Locale = (typeof LOCALES)[number];

interface QueueCard {
  id: string;
  kind: Kind;
  slug: string;
  title: Record<string, string>;
  summary: Record<string, string>;
  source_name: string;
  source_url: string;
  published_at: string;
  canonical_url: string | null;
  language: string;
  duration_seconds: number | null;
  video_provider: string | null;
  moderation_status: StatusKey;
}

function pick(text: Record<string, string>): string {
  return text.en ?? Object.values(text)[0] ?? "—";
}

/** Which locales this item actually has, so a reviewer can see at a
 * glance that a feed item is English-only rather than assuming it was
 * translated. */
function localeChips(item: QueueCard): string {
  return LOCALES.filter((l) => item.title[l]?.trim())
    .join(" · ")
    .toUpperCase();
}

function Chip({
  label,
  tone = "ghost",
}: {
  label: string;
  tone?: "ghost" | "warn";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center self-start rounded-pill border px-[9px] py-[3px] text-[11px] font-extrabold",
        tone === "warn"
          ? "border-alert-line bg-alert-bg text-ink"
          : "border-line bg-ghost text-ink",
      )}
    >
      {label}
    </span>
  );
}

export function ContentManager() {
  const [status, setStatus] = useState<StatusKey>("pending");
  const [items, setItems] = useState<QueueCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const { toast } = useToast();

  const load = useCallback(
    async (which: StatusKey) => {
      setLoading(true);
      try {
        const body = await getJson(`/content/queue?status=${which}&limit=50`);
        setItems((body.items as QueueCard[]) ?? []);
      } catch (error) {
        setItems([]);
        toast({
          title:
            error instanceof ApiError && error.status === 403
              ? "You do not have content.read on this account."
              : "Could not load the queue.",
        });
      } finally {
        setLoading(false);
      }
    },
    [toast],
  );

  useEffect(() => {
    void load(status);
  }, [load, status]);

  async function moderate(item: QueueCard, next: StatusKey) {
    setBusy(item.id);
    try {
      await postJson(`/content/items/${item.id}/moderation`, { status: next });
      // Drop it from the current list rather than refetching the page:
      // the row has left this status by definition.
      setItems((current) => current.filter((row) => row.id !== item.id));
      toast({
        title: `${item.slug} → ${next}`,
      });
    } catch (error) {
      toast({
        title:
          error instanceof ApiError && error.status === 403
            ? "Publishing needs content.publish — approving is a separate permission from drafting."
            : "That did not go through.",
      });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-2xl font-extrabold text-ink">
          Content
        </h1>
        <p className="mt-1 max-w-[70ch] text-sm text-sub">
          Nothing on agri.in publishes itself. Ingested news, drafted guides and
          pest advisories all arrive here first, and stay invisible to readers
          until someone approves them.
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        {STATUSES.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setStatus(tab.key)}
            aria-current={status === tab.key ? "page" : undefined}
            className={cn(
              "min-h-[44px] rounded-pill border px-4 text-sm font-bold",
              status === tab.key
                ? "border-brand bg-brand text-white"
                : "border-line bg-card text-ink",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-sm text-sub">Loading…</p>
      ) : items.length === 0 ? (
        <p className="rounded-card border border-line bg-card p-5 text-sm text-sub">
          {status === "pending"
            ? "Queue is clear — nothing is waiting for review."
            : `Nothing ${status}.`}
        </p>
      ) : (
        <ul className="grid list-none gap-3 p-0">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex flex-col gap-2 rounded-card border border-line bg-card p-4"
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <Chip label={item.kind} />
                <Chip label={localeChips(item) || "NO TITLE"} />
                {/* An advisory with no window would never be served, so
                    flag it here rather than letting a reviewer approve
                    something that will silently never appear. */}
                {item.kind === "advisory" ? (
                  <Chip label="needs window + districts" tone="warn" />
                ) : null}
                {item.kind === "video" && !item.duration_seconds ? (
                  <Chip label="no duration" tone="warn" />
                ) : null}
              </div>

              <p className="text-sm font-semibold text-ink">
                {pick(item.title)}
              </p>
              <p className="text-xs leading-[1.5] text-sub">
                {pick(item.summary)}
              </p>

              {/* The attribution a reviewer is actually checking. */}
              <p className="text-[11px] text-sub">
                <b className="font-semibold text-ink">{item.source_name}</b>
                {" · "}
                {new Date(item.published_at).toLocaleDateString("en-IN", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
                {" · "}
                <code className="text-[10.5px]">{item.slug}</code>
              </p>
              {item.canonical_url ? (
                <a
                  href={item.canonical_url}
                  target="_blank"
                  rel="noopener nofollow"
                  className="text-[11.5px] font-semibold text-brand no-underline"
                >
                  Read the original before approving →
                </a>
              ) : null}

              <div className="mt-1 flex flex-wrap gap-2">
                {item.moderation_status !== "approved" ? (
                  <button
                    type="button"
                    disabled={busy === item.id}
                    onClick={() => void moderate(item, "approved")}
                    className="min-h-[44px] rounded-btn bg-brand px-4 text-sm font-bold text-white disabled:opacity-60"
                  >
                    Approve &amp; publish
                  </button>
                ) : (
                  // Reversible by the same door it came through — an
                  // approval made in error must not need a DB edit.
                  <button
                    type="button"
                    disabled={busy === item.id}
                    onClick={() => void moderate(item, "pending")}
                    className="min-h-[44px] rounded-btn border border-line bg-card px-4 text-sm font-bold text-ink disabled:opacity-60"
                  >
                    Unpublish
                  </button>
                )}
                {item.moderation_status !== "rejected" ? (
                  <button
                    type="button"
                    disabled={busy === item.id}
                    onClick={() => void moderate(item, "rejected")}
                    className="min-h-[44px] rounded-btn border border-line bg-card px-4 text-sm font-bold text-ink disabled:opacity-60"
                  >
                    Reject
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      <ContentComposer onCreated={() => void load(status)} />
    </div>
  );
}

const EMPTY_I18N = { en: "", ta: "", hi: "" };

/**
 * The draft composer.
 *
 * Behind `content.write`, which is NOT `content.publish` — an editor who
 * can write cannot approve their own work. Saving always produces a
 * `pending` row; there is no publish path from this form because the API
 * has no field for one.
 */
function ContentComposer({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<Kind>("guide");
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState<Record<string, string>>(EMPTY_I18N);
  const [summary, setSummary] = useState<Record<string, string>>(EMPTY_I18N);
  const [body, setBody] = useState<Record<string, string>>(EMPTY_I18N);
  const [sourceName, setSourceName] = useState("agri.in");
  const [sourceUrl, setSourceUrl] = useState("https://agri.in/");
  const [language, setLanguage] = useState<Locale>("en");
  const [videoProvider, setVideoProvider] = useState("youtube");
  const [videoId, setVideoId] = useState("");
  const [duration, setDuration] = useState("");
  const [districts, setDistricts] = useState("");
  const [windowStart, setWindowStart] = useState("");
  const [windowEnd, setWindowEnd] = useState("");
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  function setLocale(
    setter: (next: Record<string, string>) => void,
    current: Record<string, string>,
    locale: Locale,
    value: string,
  ) {
    setter({ ...current, [locale]: value });
  }

  /** Strip the empty locales: an untranslated field must be ABSENT, not
   * an empty string, so the reader-side fallback to English works and a
   * blank card is impossible. */
  function compact(text: Record<string, string>): Record<string, string> {
    return Object.fromEntries(Object.entries(text).filter(([, v]) => v.trim()));
  }

  async function save() {
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        kind,
        slug,
        title: compact(title),
        summary: compact(summary),
        source_name: sourceName,
        source_url: sourceUrl,
        published_at: new Date().toISOString(),
        language,
        verticals: [],
        states: [],
      };
      const compactBody = compact(body);
      if (Object.keys(compactBody).length) payload.body = compactBody;
      if (kind === "video") {
        payload.video_provider = videoProvider;
        payload.video_id = videoId;
        // Curator-entered: no keyless official API reports YouTube
        // duration. Left out entirely when unknown, so the card renders
        // without the pill rather than showing an invented time.
        if (duration.trim()) payload.duration_seconds = Number(duration);
      }
      if (kind === "advisory") {
        payload.districts = districts
          .split(",")
          .map((d) => d.trim())
          .filter(Boolean);
        if (windowStart) payload.window_start = windowStart;
        if (windowEnd) payload.window_end = windowEnd;
      }

      await postJson("/content/items", payload);
      toast({
        title: `${slug} saved as PENDING — approve it above.`,
      });
      setSlug("");
      setTitle(EMPTY_I18N);
      setSummary(EMPTY_I18N);
      setBody(EMPTY_I18N);
      setVideoId("");
      setDuration("");
      onCreated();
    } catch (error) {
      toast({
        title:
          error instanceof ApiError
            ? error.status === 409
              ? "That slug is taken. Slugs are immutable, so they cannot be reused."
              : error.detail
            : "Could not save.",
      });
    } finally {
      setSaving(false);
    }
  }

  const inputClass =
    "min-h-[44px] w-full rounded-btn border border-line bg-card px-3 text-sm text-ink";

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="min-h-[44px] rounded-btn border border-line bg-card px-4 text-sm font-bold text-ink"
      >
        + Draft a guide, advisory or video
      </button>
    );
  }

  return (
    <section className="space-y-3 rounded-card border border-line bg-card p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-display text-lg font-extrabold text-ink">
          New draft
        </h2>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="tap-target text-sm font-bold text-brand"
        >
          Close
        </button>
      </div>
      <p className="text-xs text-sub">
        Saves as <b>pending</b>. There is no publish button here — approving is
        a separate permission, and the API has no field that would let this form
        skip it.
      </p>

      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-xs font-semibold text-ink">
          Kind
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as Kind)}
            className={inputClass}
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-semibold text-ink">
          Slug (permanent — it becomes the URL)
          <input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="paddy-nursery-in-14-days"
            className={inputClass}
          />
        </label>
        <label className="text-xs font-semibold text-ink">
          Source name (shown as attribution)
          <input
            value={sourceName}
            onChange={(e) => setSourceName(e.target.value)}
            className={inputClass}
          />
        </label>
        <label className="text-xs font-semibold text-ink">
          Source URL
          <input
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            className={inputClass}
          />
        </label>
        <label className="text-xs font-semibold text-ink">
          Language of the material
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value as Locale)}
            className={inputClass}
          >
            {LOCALES.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </label>
      </div>

      {kind === "video" ? (
        <div className="grid gap-3 md:grid-cols-3">
          <label className="text-xs font-semibold text-ink">
            Provider (allowlisted)
            <select
              value={videoProvider}
              onChange={(e) => setVideoProvider(e.target.value)}
              className={inputClass}
            >
              <option value="youtube">youtube</option>
              <option value="vimeo">vimeo</option>
            </select>
          </label>
          <label className="text-xs font-semibold text-ink">
            Video id (not the URL)
            <input
              value={videoId}
              onChange={(e) => setVideoId(e.target.value)}
              className={inputClass}
            />
          </label>
          <label className="text-xs font-semibold text-ink">
            Duration in seconds (leave blank if unsure)
            <input
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              inputMode="numeric"
              className={inputClass}
            />
          </label>
        </div>
      ) : null}

      {kind === "advisory" ? (
        <div className="grid gap-3 md:grid-cols-3">
          <label className="text-xs font-semibold text-ink">
            Districts (comma separated; blank = everywhere)
            <input
              value={districts}
              onChange={(e) => setDistricts(e.target.value)}
              placeholder="Coimbatore, Erode"
              className={inputClass}
            />
          </label>
          <label className="text-xs font-semibold text-ink">
            Window starts
            <input
              type="date"
              value={windowStart}
              onChange={(e) => setWindowStart(e.target.value)}
              className={inputClass}
            />
          </label>
          <label className="text-xs font-semibold text-ink">
            Window ends
            <input
              type="date"
              value={windowEnd}
              onChange={(e) => setWindowEnd(e.target.value)}
              className={inputClass}
            />
          </label>
        </div>
      ) : null}
      {kind === "advisory" ? (
        <p className="rounded-btn border border-alert-line bg-alert-bg p-2.5 text-[11.5px] text-ink">
          An advisory with no start date is never served — a pest alert that
          cannot expire is a notice. Set the window to the weeks it is actually
          true for.
        </p>
      ) : null}

      {[
        ["Title", title, setTitle] as const,
        ["Summary", summary, setSummary] as const,
        ["Body", body, setBody] as const,
      ].map(([label, value, setter]) => (
        <fieldset key={label} className="rounded-btn border border-line p-3">
          <legend className="px-1 text-xs font-bold text-ink">{label}</legend>
          <div className="grid gap-2 md:grid-cols-3">
            {LOCALES.map((locale) => (
              <label
                key={locale}
                className="text-[11px] font-semibold uppercase text-sub"
              >
                {locale}
                <textarea
                  value={value[locale] ?? ""}
                  onChange={(e) =>
                    setLocale(setter, value, locale, e.target.value)
                  }
                  rows={label === "Body" ? 6 : 2}
                  className="w-full rounded-btn border border-line bg-card p-2 text-sm text-ink"
                />
              </label>
            ))}
          </div>
          <p className="mt-1 text-[10.5px] text-sub">
            Leave a language blank rather than pasting English into it — blank
            falls back to English on the site, which is honest; English labelled
            Tamil is not.
          </p>
        </fieldset>
      ))}

      <button
        type="button"
        disabled={saving || !slug.trim() || !title.en?.trim()}
        onClick={() => void save()}
        className="min-h-[44px] rounded-btn bg-brand px-5 text-sm font-bold text-white disabled:opacity-60"
      >
        {saving ? "Saving…" : "Save as pending"}
      </button>
    </section>
  );
}
