"use client";

/** Admin user console (D11.D), re-platformed onto the U3 primitives
 * (AdminDataTable + DetailDrawer). Phone renders as last-4 ONLY - the API
 * never sends more, and this component must never try to reconstruct it.
 * Every capability of the prior card-list version survives: search, open,
 * add/remove role, suspend/reactivate. */

import {
  AdminDataTable,
  Button,
  ConfirmAction,
  ConsolePageHeader,
  DetailDrawer,
  StateChip,
  cn,
  consoleControlClass,
  useToast,
  type AdminColumn,
  type ConsoleStateTone,
} from "@agri/ui";
import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

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

const STATUS_TONE: Record<AdminUser["status"], ConsoleStateTone> = {
  active: "ok",
  suspended: "alert",
  deleted: "neutral",
};

export function UsersManager() {
  const t = useTranslations("ui.admin.users");
  const { toast } = useToast();
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [items, setItems] = useState<AdminUser[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);
  const [detail, setDetail] = useState<AdminUserDetail | null>(null);

  const search = useCallback(
    async (term: string, cursor?: string) => {
      if (!term.trim()) return;
      if (cursor) setLoadingMore(true);
      else setLoading(true);
      setError(undefined);
      try {
        const params = new URLSearchParams({ q: term.trim() });
        if (cursor) params.set("cursor", cursor);
        const body = await getJson(`/users?${params}`);
        const page = body.items as AdminUser[];
        setItems((current) => (cursor ? [...current, ...page] : page));
        setNextCursor((body.next_cursor ?? null) as string | null);
        setSearched(true);
      } catch (e) {
        setError(e instanceof ApiError ? e.detail : t("error"));
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [t],
  );

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
    if (submitted) await search(submitted);
  };

  const addRole = async (role: string) => {
    if (!detail) return;
    try {
      await postJson(`/users/${encodeURIComponent(detail.agri_id)}/roles`, { role });
      toast({ title: t("roleAdded") });
      await refresh(detail.agri_id);
    } catch (e) {
      toast({ title: e instanceof ApiError ? e.detail : t("error") });
    }
  };

  const removeRole = async (role: string) => {
    if (!detail) return;
    try {
      await deleteJson(`/users/${encodeURIComponent(detail.agri_id)}/roles/${encodeURIComponent(role)}`);
      toast({ title: t("roleRemoved") });
      await refresh(detail.agri_id);
    } catch (e) {
      toast({ title: e instanceof ApiError ? e.detail : t("error") });
    }
  };

  const setSuspension = async (action: "suspend" | "reactivate") => {
    if (!detail) return;
    try {
      await postJson(`/users/${encodeURIComponent(detail.agri_id)}/${action}`);
      toast({ title: t(action === "suspend" ? "suspended" : "reactivated") });
      await refresh(detail.agri_id);
    } catch (e) {
      toast({ title: e instanceof ApiError ? e.detail : t("error") });
    }
  };

  const columns: readonly AdminColumn<AdminUser>[] = [
    { key: "agri_id", header: t("title"), cell: (u) => <span className="font-semibold">{u.agri_id}</span> },
    { key: "name", header: "Name", cell: (u) => u.name ?? "—", hideBelow: "md" },
    { key: "phone", header: "Phone", cell: (u) => t("phoneEnding", { last4: u.phone_last4 }), hideBelow: "lg" },
    { key: "roles", header: t("roles"), cell: (u) => u.roles.join(", ") || "—", hideBelow: "xl" },
    { key: "status", header: "Status", cell: (u) => <StateChip tone={STATUS_TONE[u.status]}>{t(`status.${u.status}`)}</StateChip> },
  ];

  return (
    <main>
      <ConsolePageHeader title={t("title")} sub={t("searchPlaceholder")} />
      <AdminDataTable
        caption={t("title")}
        columns={columns}
        rows={items}
        rowKey={(u) => u.agri_id}
        loading={loading}
        loadingMore={loadingMore}
        {...(error ? { error } : {})}
        empty={
          searched
            ? { icon: "🔍", title: t("empty") }
            : { icon: "🔍", title: t("searchLabel"), description: t("searchPlaceholder") }
        }
        nextCursor={nextCursor}
        onLoadMore={() => nextCursor && void search(submitted, nextCursor)}
        onRowOpen={(u) => void open(u.agri_id)}
        rowOpenLabel={(u) => `Open ${u.agri_id}`}
        toolbar={
          <form
            className="flex w-full max-w-md gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setSubmitted(query);
              void search(query);
            }}
          >
            <input
              className={cn(consoleControlClass, "mt-0 flex-1")}
              aria-label={t("searchLabel")}
              placeholder={t("searchPlaceholder")}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <Button type="submit" variant="brand" className="flex-none px-5">
              {t("search")}
            </Button>
          </form>
        }
      />

      <DetailDrawer
        open={detail !== null}
        onOpenChange={(next) => {
          if (!next) setDetail(null);
        }}
        title={detail?.agri_id ?? ""}
        description={detail ? (detail.name ?? undefined) : undefined}
      >
        {detail ? (
          <div className="flex flex-col gap-4 text-[13px] text-ink">
            <div className="flex items-center justify-between">
              <StateChip tone={STATUS_TONE[detail.status]}>{t(`status.${detail.status}`)}</StateChip>
              <span className="text-sub">
                {t("completion")}: {detail.completion_score}%
              </span>
            </div>
            <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1.5">
              <dt className="text-sub">{t("location")}</dt>
              <dd>{detail.district ? `${detail.district}, ${detail.state} ${detail.pincode}` : "—"}</dd>
              <dt className="text-sub">{t("language")}</dt>
              <dd>{detail.language ?? "—"}</dd>
              {detail.interests.length > 0 ? (
                <>
                  <dt className="text-sub">{t("interests")}</dt>
                  <dd>{detail.interests.join(", ")}</dd>
                </>
              ) : null}
            </dl>

            <div>
              <p className="mb-1 font-semibold">{t("roles")}</p>
              <div className="flex flex-wrap items-center gap-2">
                {detail.roles.map((role) => (
                  <button
                    key={role}
                    type="button"
                    className="tap-target rounded-pill border border-line px-3 py-1 text-[12px] text-ink"
                    aria-label={t("removeRole", { role })}
                    onClick={() => void removeRole(role)}
                  >
                    {role} ✕
                  </button>
                ))}
                <select
                  className={cn(consoleControlClass, "mt-0 w-auto")}
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
              <ConfirmAction
                trigger={<Button variant="ghost" className="flex-none px-4">{t("suspend")}</Button>}
                title={t("confirmSuspend", { agriId: detail.agri_id })}
                description={t("confirmSuspend", { agriId: detail.agri_id })}
                confirmLabel={t("suspend")}
                cancelLabel={t("cancel")}
                onConfirm={() => setSuspension("suspend")}
              />
            ) : detail.status === "suspended" ? (
              <ConfirmAction
                trigger={<Button variant="ghost" className="flex-none px-4">{t("reactivate")}</Button>}
                title={t("confirmReactivate", { agriId: detail.agri_id })}
                description={t("confirmReactivate", { agriId: detail.agri_id })}
                confirmLabel={t("reactivate")}
                cancelLabel={t("cancel")}
                onConfirm={() => setSuspension("reactivate")}
              />
            ) : null}
          </div>
        ) : null}
      </DetailDrawer>
    </main>
  );
}
