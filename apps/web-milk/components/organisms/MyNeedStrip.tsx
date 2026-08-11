import { NeedStrip } from "@agri/ui";
import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import { auth } from "@/lib/auth";
import type { ProductCategory } from "@/lib/taxonomy";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

interface NeedRoute {
  status: "new" | "responded" | "closed";
}

interface Need {
  id: string;
  status: "open" | "fulfilled" | "closed";
  payload: { qty_liters?: string; milk_type?: string; schedule?: string };
  routed_count: number;
  routes: NeedRoute[];
}

/** D25 exposes one need list per user, newest first. Five is enough to find an
 * open one without walking the cursor: a visitor with five newer closed needs
 * and an older open one is not a case worth a second round-trip on the home. */
const SCAN = 5;

/**
 * §2b — my-need status strip. Renders directly under the header ONLY when the
 * signed-in visitor has an active D25 need, exactly as U1 item 30 specifies.
 *
 * Server-rendered, not a client island: the home is already per-request
 * (`force-dynamic`), the session bearer is available here through
 * `auth.getAccessToken()`, and U1 forbids "new client-side fetch patterns
 * where the page already uses SSR". A guest has no token and the whole strip
 * costs one early `return null` — no request, no reserved space, no CLS.
 *
 * The response count is the engine's own both-side status: D25 fans a need out
 * to every covering vendor as a child inquiry, and a vendor's reply flips that
 * child to `responded`. Nothing is recomputed here.
 */
export async function MyNeedStrip({
  milkTypes,
}: {
  /** D17 milk-type values, already fetched by the page for §5c. Passed in so
   * the strip names the milk type from the schema and never from a local map
   * that would fall out of date the moment a value is added. */
  milkTypes: ProductCategory[];
}) {
  const token = await auth.getAccessToken();
  if (!token) return null; // guest — the strip is user state

  let needs: Need[] = [];
  try {
    const res = await fetch(`${API}/leads/needs/mine?limit=${SCAN}`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    needs = ((await res.json()) as { items: Need[] }).items;
  } catch {
    return null; // the home must not break because a personalised strip failed
  }

  const active = needs.find((need) => need.status === "open");
  if (!active) return null;

  const t = await getTranslations("ui.home.myNeed");
  const type = milkTypes.find((option) => option.value === active.payload.milk_type);
  const schedule = active.payload.schedule ?? "";
  const summary = [
    active.payload.qty_liters ? t("litres", { qty: active.payload.qty_liters }) : "",
    type?.label ?? "",
    // The D25 schedule enum is a fixed set on the post-need form, so its labels
    // are i18n content (allowed) rather than a value set with a registry.
    schedule ? t(`schedule.${schedule}` as "schedule.daily") : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const responded = active.routes.filter((route) => route.status === "responded").length;

  return (
    <NeedStrip
      data-testid="my-need-strip"
      icon="🥛"
      action={
        <Link href="/my-needs" prefetch={false} className="no-underline">
          {t("view")}
        </Link>
      }
    >
      {t("label")} <b className="text-ink">{summary}</b> —{" "}
      <b className="text-ink">{t("responded", { count: responded })}</b>
    </NeedStrip>
  );
}
