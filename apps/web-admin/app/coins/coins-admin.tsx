"use client";

/**
 * Admin AgriCoins console (D13.19): rules CRUD (flag-gated), dual-confirm
 * manual balance adjust, abuse-flag queue with void-via-compensating-entries.
 *
 * AgriCoins are not money - there is no purchase/cash-out UI here, only
 * integer ledger controls. The manual-adjust flow is deliberately TWO
 * distinct clicks (submit, then a separate "Confirm adjustment" click) as
 * an insider-manipulation guard: the first click only requests an opaque,
 * short-lived confirmation_token from POST /coins/adjust and writes
 * nothing; only the second click's POST /coins/adjust/confirm applies it.
 */

import { Button, Card, EmptyState, Modal, Skeleton, useToast } from "@agri/ui";
import { useEffect, useState } from "react";

import { ApiError, getJson, postJson, putJson } from "@/lib/api";

interface Rule {
  code: string;
  amount: number;
  daily_cap: number | null;
  weekly_cap: number | null;
  total_cap: number | null;
  active: boolean;
  valid_from: string | null;
  valid_to: string | null;
}

interface RuleDraft {
  amount: string;
  daily_cap: string;
  weekly_cap: string;
  total_cap: string;
  active: boolean;
  valid_from: string;
  valid_to: string;
}

interface AbuseFlag {
  id: string;
  referral_id: string;
  cluster_reason: string;
  status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
}

function isoToLocalInput(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(0, 16);
}

function draftFromRule(rule: Rule): RuleDraft {
  return {
    amount: String(rule.amount),
    daily_cap: rule.daily_cap === null ? "" : String(rule.daily_cap),
    weekly_cap: rule.weekly_cap === null ? "" : String(rule.weekly_cap),
    total_cap: rule.total_cap === null ? "" : String(rule.total_cap),
    active: rule.active,
    valid_from: isoToLocalInput(rule.valid_from),
    valid_to: isoToLocalInput(rule.valid_to),
  };
}

/** Only fields the admin actually set are sent - the API treats an absent
 * field as "no change" (it does not accept explicit nulls to clear a cap or
 * window bound), so blank inputs are simply omitted rather than nulled. */
function buildRulePayload(draft: RuleDraft): Record<string, unknown> {
  const payload: Record<string, unknown> = { active: draft.active };
  const amount = Number(draft.amount);
  if (Number.isInteger(amount) && amount > 0) payload.amount = amount;
  for (const key of ["daily_cap", "weekly_cap", "total_cap"] as const) {
    const raw = draft[key].trim();
    if (raw === "") continue;
    const parsed = Number(raw);
    if (Number.isInteger(parsed)) payload[key] = parsed;
  }
  if (draft.valid_from) payload.valid_from = new Date(draft.valid_from).toISOString();
  if (draft.valid_to) payload.valid_to = new Date(draft.valid_to).toISOString();
  return payload;
}

function AlertNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

function RulesSection() {
  const { toast } = useToast();
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [disabled, setDisabled] = useState(false);
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const [draft, setDraft] = useState<RuleDraft | null>(null);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const body = await getJson("/coins/rules");
      setRules(body as unknown as Rule[]);
    } catch {
      toast({ title: "Could not load rules" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const startEdit = (rule: Rule) => {
    setEditingCode(rule.code);
    setDraft(draftFromRule(rule));
  };

  const cancelEdit = () => {
    setEditingCode(null);
    setDraft(null);
  };

  const save = async (code: string) => {
    if (!draft) return;
    setSaving(true);
    try {
      const updated = await putJson(`/coins/rules/${encodeURIComponent(code)}`, buildRulePayload(draft));
      setRules((prev) => prev.map((rule) => (rule.code === code ? (updated as unknown as Rule) : rule)));
      setDisabled(false);
      toast({ title: `Rule ${code} updated` });
      cancelEdit();
    } catch (error) {
      if (error instanceof ApiError && error.detail === "rules_admin_disabled") {
        setDisabled(true);
      } else {
        toast({ title: error instanceof ApiError ? error.detail : "Could not update rule" });
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="space-y-3 p-4">
      <h2 className="font-display text-lg font-extrabold text-ink">Rules</h2>
      {disabled ? (
        <AlertNotice>
          Rules editing is disabled by feature flag (coins_rules_admin is off). Turn the flag on to
          edit reward rules.
        </AlertNotice>
      ) : null}
      {loading ? (
        <div className="space-y-2">
          <Skeleton width="100%" height="56px" />
          <Skeleton width="100%" height="56px" />
        </div>
      ) : rules.length === 0 ? (
        <EmptyState icon="🪙" title="No rules configured" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-sm text-ink">
            <thead>
              <tr className="border-b border-line text-left text-sub">
                <th className="py-2 pr-2">Code</th>
                <th className="py-2 pr-2">Amount</th>
                <th className="py-2 pr-2">Daily cap</th>
                <th className="py-2 pr-2">Weekly cap</th>
                <th className="py-2 pr-2">Total cap</th>
                <th className="py-2 pr-2">Active</th>
                <th className="py-2 pr-2">Window</th>
                <th className="py-2 pr-2" />
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => {
                const isEditing = editingCode === rule.code && draft;
                return (
                  <tr key={rule.code} className="border-b border-line align-top">
                    <td className="py-2 pr-2 font-semibold">{rule.code}</td>
                    {isEditing && draft ? (
                      <>
                        <td className="py-2 pr-2">
                          <input
                            type="number"
                            step={1}
                            min={1}
                            className="min-h-[44px] w-24 rounded-btn border border-line bg-card px-2 py-1 text-ink"
                            aria-label={`Amount for ${rule.code}`}
                            value={draft.amount}
                            onChange={(event) => setDraft({ ...draft, amount: event.target.value })}
                          />
                        </td>
                        <td className="py-2 pr-2">
                          <input
                            type="number"
                            step={1}
                            className="min-h-[44px] w-24 rounded-btn border border-line bg-card px-2 py-1 text-ink"
                            aria-label={`Daily cap for ${rule.code}`}
                            placeholder="no cap"
                            value={draft.daily_cap}
                            onChange={(event) => setDraft({ ...draft, daily_cap: event.target.value })}
                          />
                        </td>
                        <td className="py-2 pr-2">
                          <input
                            type="number"
                            step={1}
                            className="min-h-[44px] w-24 rounded-btn border border-line bg-card px-2 py-1 text-ink"
                            aria-label={`Weekly cap for ${rule.code}`}
                            placeholder="no cap"
                            value={draft.weekly_cap}
                            onChange={(event) => setDraft({ ...draft, weekly_cap: event.target.value })}
                          />
                        </td>
                        <td className="py-2 pr-2">
                          <input
                            type="number"
                            step={1}
                            className="min-h-[44px] w-24 rounded-btn border border-line bg-card px-2 py-1 text-ink"
                            aria-label={`Total cap for ${rule.code}`}
                            placeholder="no cap"
                            value={draft.total_cap}
                            onChange={(event) => setDraft({ ...draft, total_cap: event.target.value })}
                          />
                        </td>
                        <td className="py-2 pr-2">
                          <input
                            type="checkbox"
                            className="h-[22px] w-[22px]"
                            aria-label={`Active for ${rule.code}`}
                            checked={draft.active}
                            onChange={(event) => setDraft({ ...draft, active: event.target.checked })}
                          />
                        </td>
                        <td className="py-2 pr-2">
                          <div className="flex flex-col gap-1">
                            <input
                              type="datetime-local"
                              className="min-h-[44px] rounded-btn border border-line bg-card px-2 py-1 text-ink"
                              aria-label={`Valid from for ${rule.code}`}
                              value={draft.valid_from}
                              onChange={(event) => setDraft({ ...draft, valid_from: event.target.value })}
                            />
                            <input
                              type="datetime-local"
                              className="min-h-[44px] rounded-btn border border-line bg-card px-2 py-1 text-ink"
                              aria-label={`Valid to for ${rule.code}`}
                              value={draft.valid_to}
                              onChange={(event) => setDraft({ ...draft, valid_to: event.target.value })}
                            />
                          </div>
                        </td>
                        <td className="py-2 pr-2">
                          <div className="flex flex-col gap-2">
                            <Button variant="brand" disabled={saving} onClick={() => void save(rule.code)}>
                              Save
                            </Button>
                            <Button disabled={saving} onClick={cancelEdit}>
                              Cancel
                            </Button>
                          </div>
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="py-2 pr-2">{rule.amount}</td>
                        <td className="py-2 pr-2">{rule.daily_cap ?? "—"}</td>
                        <td className="py-2 pr-2">{rule.weekly_cap ?? "—"}</td>
                        <td className="py-2 pr-2">{rule.total_cap ?? "—"}</td>
                        <td className="py-2 pr-2">{rule.active ? "Yes" : "No"}</td>
                        <td className="py-2 pr-2 text-sub">
                          {rule.valid_from ? new Date(rule.valid_from).toLocaleString() : "—"}
                          {" → "}
                          {rule.valid_to ? new Date(rule.valid_to).toLocaleString() : "—"}
                        </td>
                        <td className="py-2 pr-2">
                          <Button onClick={() => startEdit(rule)}>Edit</Button>
                        </td>
                      </>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

type AdjustStage = "form" | "review" | "done";

function ManualAdjustSection() {
  const { toast } = useToast();
  const [userId, setUserId] = useState("");
  const [delta, setDelta] = useState("");
  const [reasonNote, setReasonNote] = useState("");
  const [stage, setStage] = useState<AdjustStage>("form");
  const [pending, setPending] = useState<{ user_id: string; delta: number; reason_note: string } | null>(
    null,
  );
  const [token, setToken] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [resultBalance, setResultBalance] = useState<number | null>(null);

  const reset = () => {
    setUserId("");
    setDelta("");
    setReasonNote("");
    setStage("form");
    setPending(null);
    setToken(null);
    setErrorMessage(null);
    setResultBalance(null);
  };

  /** Click 1 of 2: requests a confirmation_token only. Writes nothing. */
  const requestAdjust = async (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    const parsedDelta = Number(delta);
    if (!userId.trim()) {
      setErrorMessage("user_id is required.");
      return;
    }
    if (!Number.isInteger(parsedDelta) || parsedDelta === 0) {
      setErrorMessage("delta must be a non-zero whole number.");
      return;
    }
    if (!reasonNote.trim()) {
      setErrorMessage("reason_note is required.");
      return;
    }
    setSubmitting(true);
    try {
      const body = await postJson("/coins/adjust", {
        user_id: userId.trim(),
        delta: parsedDelta,
        reason_note: reasonNote.trim(),
      });
      setPending({ user_id: userId.trim(), delta: parsedDelta, reason_note: reasonNote.trim() });
      setToken(body.confirmation_token as string);
      setStage("review");
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.detail : "Could not start the adjustment.");
    } finally {
      setSubmitting(false);
    }
  };

  /** Click 2 of 2: the ONLY action that actually applies the adjustment. */
  const confirmAdjust = async () => {
    if (!token) return;
    setSubmitting(true);
    setErrorMessage(null);
    try {
      const body = await postJson("/coins/adjust/confirm", { confirmation_token: token });
      setResultBalance(body.balance as number);
      setStage("done");
      toast({ title: "Adjustment applied" });
    } catch (error) {
      if (error instanceof ApiError && error.detail === "insufficient_balance") {
        setErrorMessage("Cannot apply: this would overdraw the user's balance.");
      } else if (error instanceof ApiError && error.detail === "invalid_or_expired_token") {
        setErrorMessage("This confirmation has expired or was already used. Start over.");
      } else {
        setErrorMessage("Could not apply the adjustment.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="space-y-3 p-4">
      <h2 className="font-display text-lg font-extrabold text-ink">Manual balance adjust</h2>
      <p className="text-[13px] text-sub">
        Two separate clicks are required: submitting only requests a confirmation; nothing is written
        until you press &quot;Confirm adjustment&quot;.
      </p>
      {errorMessage ? <AlertNotice>{errorMessage}</AlertNotice> : null}

      {stage === "form" ? (
        <form className="space-y-2" onSubmit={(event) => void requestAdjust(event)}>
          <label className="block text-sm font-semibold text-ink">
            User ID (UUID)
            <input
              className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              required
            />
          </label>
          <label className="block text-sm font-semibold text-ink">
            Delta (signed whole number, non-zero)
            <input
              type="number"
              step={1}
              className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
              value={delta}
              onChange={(event) => setDelta(event.target.value)}
              placeholder="-50 or 50"
              required
            />
          </label>
          <label className="block text-sm font-semibold text-ink">
            Reason note
            <input
              className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
              value={reasonNote}
              onChange={(event) => setReasonNote(event.target.value)}
              placeholder="Why is this adjustment being made?"
              required
            />
          </label>
          <Button type="submit" variant="brand" disabled={submitting}>
            Request adjustment
          </Button>
        </form>
      ) : null}

      {stage === "review" && pending ? (
        <div className="space-y-3 rounded-card border border-line bg-ghost p-3">
          <p className="text-sm font-semibold text-ink">Confirm this adjustment:</p>
          <ul className="text-sm text-ink">
            <li>
              User: <span className="font-semibold">{pending.user_id}</span>
            </li>
            <li>
              Delta: <span className="font-semibold">{pending.delta > 0 ? `+${pending.delta}` : pending.delta}</span>
            </li>
            <li>
              Reason: <span className="font-semibold">{pending.reason_note}</span>
            </li>
          </ul>
          <div className="flex gap-2">
            <Button variant="brand" disabled={submitting} onClick={() => void confirmAdjust()}>
              Confirm adjustment
            </Button>
            <Button disabled={submitting} onClick={reset}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}

      {stage === "done" && resultBalance !== null ? (
        <div className="space-y-2 rounded-card border border-line bg-ghost p-3">
          <p className="text-sm font-semibold text-ink">
            Adjustment applied. New balance: <span className="font-extrabold">{resultBalance}</span>
          </p>
          <Button onClick={reset}>Make another adjustment</Button>
        </div>
      ) : null}
    </Card>
  );
}

function AbuseSection() {
  const { toast } = useToast();
  const [items, setItems] = useState<AbuseFlag[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [voidingId, setVoidingId] = useState<string | null>(null);

  const load = async (cursor?: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "20" });
      if (cursor) params.set("cursor", cursor);
      const body = await getJson(`/coins/abuse?${params}`);
      const page = body.items as AbuseFlag[];
      setItems(cursor ? [...items, ...page] : page);
      setNextCursor((body.next_cursor ?? null) as string | null);
    } catch {
      toast({ title: "Could not load abuse queue" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const voidFlag = async (flagId: string) => {
    setVoidingId(flagId);
    try {
      const body = await postJson(`/coins/abuse/${encodeURIComponent(flagId)}/void`);
      setItems((prev) => prev.filter((flag) => flag.id !== flagId));
      toast({ title: `Voided — ${body.reversed_count} entr${body.reversed_count === 1 ? "y" : "ies"} reversed` });
    } catch (error) {
      if (error instanceof ApiError && error.detail === "cannot_void_insufficient_balance") {
        toast({ title: "Cannot void: user already spent these coins" });
      } else {
        toast({ title: error instanceof ApiError ? error.detail : "Could not void this flag" });
      }
    } finally {
      setVoidingId(null);
    }
  };

  return (
    <Card className="space-y-3 p-4">
      <h2 className="font-display text-lg font-extrabold text-ink">Abuse queue</h2>
      {loading && items.length === 0 ? (
        <div className="space-y-2">
          <Skeleton width="100%" height="72px" />
          <Skeleton width="100%" height="72px" />
        </div>
      ) : null}
      {!loading && items.length === 0 ? <EmptyState icon="🚩" title="No open abuse flags" /> : null}
      <ul className="space-y-2">
        {items.map((flag) => (
          <li key={flag.id}>
            <Card className="space-y-2 p-3">
              <p className="font-semibold text-ink">Referral {flag.referral_id}</p>
              <p className="text-sm text-sub">
                Reason: {flag.cluster_reason} · Flagged {new Date(flag.created_at).toLocaleString()}
              </p>
              <Modal
                trigger={<Button variant="brand">Void (reverses via compensating entries)</Button>}
                title="Void this referral cluster?"
                description="This reverses the referral's coin awards with compensating ledger entries. It never edits or deletes the original entries. If a recipient already spent the coins, the void is rejected."
                closeLabel="Cancel"
              >
                <Button
                  variant="brand"
                  disabled={voidingId === flag.id}
                  onClick={() => void voidFlag(flag.id)}
                >
                  Confirm void
                </Button>
              </Modal>
            </Card>
          </li>
        ))}
      </ul>
      {nextCursor ? <Button onClick={() => void load(nextCursor)}>Load more</Button> : null}
    </Card>
  );
}

export function CoinsAdmin() {
  return (
    <main className="mx-auto max-w-4xl space-y-6 p-4">
      <h1 className="text-xl font-bold text-ink">AgriCoins admin</h1>
      <RulesSection />
      <ManualAdjustSection />
      <AbuseSection />
    </main>
  );
}
