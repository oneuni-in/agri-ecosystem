"use client";

/** Admin user console (D11.D). Phone renders as last-4 ONLY - the API never
 * sends more, and this component must never try to reconstruct it. */

import { Button, Card, EmptyState, Modal, Skeleton, cn, useToast } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ApiError, deleteJson, getJson, postJson } from "@/lib/api";

interface AdminUser {
  agri_id: string;
  phone_last4: string;
  status: "active" | "suspended" | "deleted";
  name: string | null;
  roles: string[];
  created_at: string;
}

interface AdminUserDetail extends AdminUser {
  state: string | null;
  district: string | null;
  pincode: string | null;
  language: string | null;
  interests: string[];
  has_avatar: boolean;
  completion_score: number;
}

const ASSIGNABLE_ROLES = ["user", "farmer", "business_owner", "staff", "super_admin"] as const;

/** Badge's variant union (sponsored/verified/cert) is fixed marketing
 * semantics with fixed palettes - it doesn't model a 3-state account status,
 * so status renders as a plain token-styled pill instead of stretching Badge
 * to a meaning it wasn't built for. */
function StatusPill({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center self-start rounded-pill border border-line bg-ghost px-[9px] py-[3px] text-[11px] font-extrabold text-ink">
      {label}
    </span>
  );
}

export function UsersManager() {
  const t = useTranslations("ui.admin.users");
  const { toast } = useToast();
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<AdminUser[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<AdminUserDetail | null>(null);

  const search = async (cursor?: string) => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ q: query.trim() });
      if (cursor) params.set("cursor", cursor);
      const body = await getJson(`/users?${params}`);
      const page = body.items as AdminUser[];
      setItems(cursor ? [...items, ...page] : page);
      setNextCursor((body.next_cursor ?? null) as string | null);
      setSearched(true);
    } catch {
      toast({ title: t("error") });
    } finally {
      setLoading(false);
    }
  };

  const open = async (agriId: string) => {
    try {
      const body = await getJson(`/users/${encodeURIComponent(agriId)}`);
      setDetail(body as unknown as AdminUserDetail);
    } catch {
      toast({ title: t("error") });
    }
  };

  const refresh = async (agriId: string) => {
    await open(agriId);
    await search();
  };

  const addRole = async (role: string) => {
    if (!detail) return;
    try {
      await postJson(`/users/${encodeURIComponent(detail.agri_id)}/roles`, { role });
      toast({ title: t("roleAdded") });
      await refresh(detail.agri_id);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : t("error") });
    }
  };

  const removeRole = async (role: string) => {
    if (!detail) return;
    try {
      await deleteJson(`/users/${encodeURIComponent(detail.agri_id)}/roles/${encodeURIComponent(role)}`);
      toast({ title: t("roleRemoved") });
      await refresh(detail.agri_id);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : t("error") });
    }
  };

  const setSuspension = async (action: "suspend" | "reactivate") => {
    if (!detail) return;
    try {
      await postJson(`/users/${encodeURIComponent(detail.agri_id)}/${action}`);
      toast({ title: t(action === "suspend" ? "suspended" : "reactivated") });
      await refresh(detail.agri_id);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : t("error") });
    }
  };

  return (
    <main className="mx-auto max-w-3xl space-y-4 p-4">
      <h1 className="text-xl font-bold text-ink">{t("title")}</h1>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void search();
        }}
      >
        <input
          className="min-h-[44px] min-w-0 flex-1 rounded-btn border border-line bg-card px-3 py-2 text-ink"
          aria-label={t("searchLabel")}
          placeholder={t("searchPlaceholder")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button type="submit" variant="brand">
          {t("search")}
        </Button>
      </form>

      {loading && items.length === 0 ? (
        <div className="space-y-2">
          <Skeleton width="100%" height="72px" />
          <Skeleton width="100%" height="72px" />
        </div>
      ) : null}
      {searched && !loading && items.length === 0 ? <EmptyState icon="🔍" title={t("empty")} /> : null}

      <ul className="space-y-2">
        {items.map((user) => (
          <li key={user.agri_id}>
            <Card
              hover
              className={cn("cursor-pointer p-3", detail?.agri_id === user.agri_id && "border-brand")}
              onClick={() => void open(user.agri_id)}
            >
              <div className="flex items-center justify-between gap-2">
                <div>
                  <p className="font-semibold text-ink">{user.agri_id}</p>
                  <p className="text-sm text-sub">
                    {user.name ?? "—"} · {t("phoneEnding", { last4: user.phone_last4 })}
                  </p>
                </div>
                <StatusPill label={t(`status.${user.status}`)} />
              </div>
            </Card>
          </li>
        ))}
      </ul>
      {nextCursor ? (
        <Button onClick={() => void search(nextCursor)}>{t("loadMore")}</Button>
      ) : null}

      {detail ? (
        <Card className="space-y-3 p-4">
          <div className="flex items-center justify-between">
            <p className="font-semibold text-ink">{detail.agri_id}</p>
            <StatusPill label={t(`status.${detail.status}`)} />
          </div>
          <p className="text-sm text-sub">
            {t("completion")}: {detail.completion_score}% · {t("location")}:{" "}
            {detail.district ? `${detail.district}, ${detail.state} ${detail.pincode}` : "—"} ·{" "}
            {t("language")}: {detail.language ?? "—"}
          </p>
          {detail.interests.length > 0 ? (
            <p className="text-sm text-sub">
              {t("interests")}: {detail.interests.join(", ")}
            </p>
          ) : null}
          <div>
            <p className="text-sm font-semibold text-ink">{t("roles")}</p>
            <div className="mt-1 flex flex-wrap gap-2">
              {detail.roles.map((role) => (
                <button
                  key={role}
                  type="button"
                  className="tap-target rounded-pill border border-line px-3 py-1 text-sm text-ink"
                  aria-label={t("removeRole", { role })}
                  onClick={() => void removeRole(role)}
                >
                  {role} ✕
                </button>
              ))}
              <select
                className="min-h-[44px] rounded-btn border border-line bg-card px-2 py-1 text-sm text-ink"
                aria-label={t("addRole")}
                value=""
                onChange={(event) => {
                  if (event.target.value) void addRole(event.target.value);
                }}
              >
                <option value="">{t("addRole")}</option>
                {ASSIGNABLE_ROLES.filter((role) => !detail.roles.includes(role)).map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {detail.status === "active" ? (
            <Modal
              key="suspend"
              trigger={<Button variant="brand">{t("suspend")}</Button>}
              title={t("confirmSuspend", { agriId: detail.agri_id })}
              closeLabel={t("cancel")}
            >
              <Button variant="brand" onClick={() => void setSuspension("suspend")}>
                {t("suspend")}
              </Button>
            </Modal>
          ) : detail.status === "suspended" ? (
            <Modal
              key="reactivate"
              trigger={<Button variant="brand">{t("reactivate")}</Button>}
              title={t("confirmReactivate", { agriId: detail.agri_id })}
              closeLabel={t("cancel")}
            >
              <Button variant="brand" onClick={() => void setSuspension("reactivate")}>
                {t("reactivate")}
              </Button>
            </Modal>
          ) : null}
        </Card>
      ) : null}
    </main>
  );
}
