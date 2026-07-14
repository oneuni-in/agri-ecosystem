import { Card, CoinsPill, EmptyState } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const SITE = "https://id.agri.in";

// Private, always-fresh coins history — never indexed (devices/page.tsx precedent).
export const metadata: Metadata = buildMetadata({
  title: "AgriCoins history — AgriID",
  description: "Your AgriCoins balance and history",
  canonical: canonicalUrl(SITE, "/coins"),
  siteName: "AgriID",
  noIndex: true,
});

interface CoinsHistoryItem {
  id: string;
  delta: number;
  reason_code: string;
  reason_label_key: string;
  ref_type: string | null;
  created_at: string;
}

interface CoinsHistoryResponse {
  items: CoinsHistoryItem[];
  next_cursor: string | null;
}

export default async function CoinsHistoryPage({
  searchParams,
}: {
  searchParams: Promise<{ cursor?: string }>;
}) {
  const jar = await cookies();
  const sid = jar.get("agri_sid")?.value;
  if (!sid) redirect("/login?next=/coins");

  const { cursor } = await searchParams;
  const cookieHeader = { cookie: `agri_sid=${sid}` };

  const historyUrl = cursor
    ? `${API}/coins/history?cursor=${encodeURIComponent(cursor)}`
    : `${API}/coins/history`;

  const [balanceRes, historyRes, referralRes] = await Promise.all([
    fetch(`${API}/coins/balance`, { headers: cookieHeader, cache: "no-store" }),
    fetch(historyUrl, { headers: cookieHeader, cache: "no-store" }),
    fetch(`${API}/coins/referral-code`, { headers: cookieHeader, cache: "no-store" }),
  ]);

  if (balanceRes.status === 401 || historyRes.status === 401) redirect("/login?next=/coins");
  if (!balanceRes.ok || !historyRes.ok) redirect("/login?next=/coins");

  const { balance } = (await balanceRes.json()) as { balance: number };
  const history = (await historyRes.json()) as CoinsHistoryResponse;
  const referralCode = referralRes.ok
    ? ((await referralRes.json()) as { code?: string }).code ?? null
    : null;

  const t = await getTranslations();

  return (
    <main className="mx-auto flex w-full max-w-[560px] flex-col gap-4 px-4 py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-xl font-bold text-ink">{t("ui.coins.title")}</h1>
          <p className="text-sm text-sub">{t("ui.coins.subtitle")}</p>
        </div>
        <CoinsPill amount={balance.toLocaleString()} />
      </header>

      {referralCode && (
        <Card className="flex flex-col gap-2 p-4">
          <h2 className="font-display text-base font-bold text-ink">
            {t("ui.coins.referralTitle")}
          </h2>
          <p className="font-mono text-2xl font-extrabold tracking-[.1em] text-ink">
            {referralCode}
          </p>
          <p className="text-xs font-bold text-sub">{t("ui.coins.referralShare")}</p>
          <a href={`/login?ref=${referralCode}`} className="break-all text-sm text-ink">{`/login?ref=${referralCode}`}</a>
          <p className="text-xs text-sub">{t("ui.coins.referralHint")}</p>
        </Card>
      )}

      {history.items.length === 0 ? (
        <EmptyState icon="🪙" title={t("ui.coins.empty")} />
      ) : (
        <ul className="flex flex-col gap-2" data-testid="coins-history-list">
          {history.items.map((item) => (
            <li key={item.id}>
              <Card className="flex items-center justify-between gap-2 p-4">
                <div className="min-w-0">
                  <p className="truncate font-bold text-ink">{t(item.reason_label_key)}</p>
                  <p className="text-xs text-sub">
                    {new Date(item.created_at).toLocaleDateString()}
                  </p>
                </div>
                <p
                  className={
                    item.delta > 0
                      ? "shrink-0 font-extrabold text-call"
                      : "shrink-0 font-extrabold text-sub"
                  }
                >
                  {item.delta > 0 ? `+${item.delta}` : `${item.delta}`}
                </p>
              </Card>
            </li>
          ))}
        </ul>
      )}

      {history.next_cursor ? (
        <a
          href={`/coins?cursor=${encodeURIComponent(history.next_cursor)}`}
          className="mx-auto rounded-btn border border-line bg-card px-4 py-2 text-sm font-bold text-ink"
        >
          {t("ui.coins.loadMore")}
        </a>
      ) : null}
    </main>
  );
}
