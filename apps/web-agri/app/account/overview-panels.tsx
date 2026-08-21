import { Card, EmptyState, Reveal } from "@agri/ui";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import type { AccountIdentity } from "@/lib/account-identity";
import { countLabel, quotesFor, type OverviewData } from "@/lib/account-overview";

/**
 * The overview's panels (AG-U5 P2).
 *
 * All server-rendered. The only client island on this page is the alerts
 * list, because turning an alert off is the one thing here that writes.
 */

function PanelHeading({
  icon,
  title,
  href,
  action,
}: {
  icon: string;
  title: string;
  href?: string;
  action?: string;
}) {
  return (
    <div className="mb-2.5 flex items-center gap-2">
      <h2 className="font-display text-[15px] font-extrabold text-ink">
        <span aria-hidden="true" className="mr-1.5">
          {icon}
        </span>
        {title}
      </h2>
      <span className="flex-1" />
      {href && action ? (
        <Link
          href={href}
          prefetch={false}
          className="tap-target text-[12.5px] font-semibold text-brand no-underline"
        >
          {action}
        </Link>
      ) : null}
    </div>
  );
}

/**
 * The four tiles.
 *
 * Every number is `countLabel`'d, so a full page reads "20+" rather than
 * claiming a total nobody counted. The coin tile prints nothing at all when
 * the balance could not be read — a dash is not a balance.
 */
export async function StatsRow({ data }: { data: OverviewData }) {
  const t = await getTranslations("ui.account.stats");
  const { counts } = data;
  const tiles = [
    {
      key: "threads",
      label: t("threads"),
      value: countLabel(counts.activeThreads, data.inquiriesCapped || data.needsCapped),
      sub: counts.replies > 0 ? t("threadsSub", { count: counts.replies }) : t("threadsNone"),
      accent: false,
    },
    {
      key: "alerts",
      label: t("alerts"),
      value: countLabel(counts.alerts, false),
      sub: t("alertsSub"),
      accent: false,
    },
    {
      key: "saved",
      label: t("saved"),
      value: countLabel(counts.saved, data.savedCapped),
      sub: t("savedSub"),
      accent: false,
    },
    {
      key: "coins",
      label: `🪙 ${t("coins")}`,
      value: counts.coins === null ? "—" : counts.coins.toLocaleString("en-IN"),
      sub: counts.coins === null ? t("coinsUnknown") : "",
      accent: true,
    },
  ];
  return (
    <Reveal className="mt-4 grid grid-cols-2 gap-2.5 lg:grid-cols-4">
      {tiles.map((tile) => (
        <div
          key={tile.key}
          className={`rounded-card border p-3 ${
            tile.accent ? "border-alert-line bg-coins-bg" : "border-cream-line bg-card"
          }`}
        >
          <small className="block text-[10.5px] font-extrabold uppercase tracking-wide text-muted">
            {tile.label}
          </small>
          <div className="mt-0.5 font-display text-[24px] font-extrabold leading-none text-ink">
            {tile.value}
          </div>
          {tile.sub ? <div className="mt-1 text-[11.5px] text-sub">{tile.sub}</div> : null}
        </div>
      ))}
    </Reveal>
  );
}

/**
 * Enquiries and needs, newest first, three at a time.
 *
 * A need and a direct enquiry are one list here because they are one thing to
 * the person who sent them: "I asked, did anyone answer?". The difference —
 * a need fans out to several businesses, an enquiry goes to one — shows up
 * only in the reply count.
 */
export async function EnquiriesPanel({ data }: { data: OverviewData }) {
  const t = await getTranslations("ui.account.panels");
  const rows = [
    ...data.needs.map((need, index) => ({
      key: `need-${need.id ?? index}`,
      // A need fans out to several businesses; an enquiry goes to one. The
      // icon is the only place that difference shows.
      icon: "🌱",
      title: messageFrom(need.payload),
      replies: quotesFor(need),
    })),
    ...data.inquiries.map((inquiry, index) => ({
      key: `inq-${inquiry.id ?? index}`,
      icon: "📩",
      title: messageFrom(inquiry.payload),
      replies: inquiry.responses.length,
    })),
  ].slice(0, 3);

  return (
    <Card className="p-3.5">
      <PanelHeading
        icon="📩"
        title={t("enquiries")}
        href="/account/inquiries"
        action={t("enquiriesAll")}
      />
      {rows.length === 0 ? (
        <EmptyState
          icon="📭"
          title={t("enquiriesEmpty")}
          action={
            <Link
              href="/directory"
              prefetch={false}
              className="tap-target inline-flex w-full items-center justify-center rounded-pill bg-brand px-4 py-2 text-[13px] font-semibold text-white no-underline"
            >
              {t("enquiriesEmptyCta")}
            </Link>
          }
          className="border-cream-line bg-cream p-5"
        />
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => (
            <li
              key={row.key}
              className="flex items-start gap-2.5 rounded-card border border-cream-line bg-cream px-3 py-2.5"
            >
              <span aria-hidden="true" className="text-[16px] leading-none">
                {row.icon}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-semibold text-ink">
                  {row.title}
                </span>
                <span className="mt-0.5 block text-[11.5px] text-sub">
                  {row.replies > 0 ? t("quotes", { count: row.replies }) : t("quotesNone")}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/**
 * The person's own words, out of a payload whose shape varies by vertical.
 *
 * A milk enquiry carries litres and a schedule; a seed need carries a
 * sentence. Rather than switch on type, take whichever text field is present
 * — and when there is none, print an em dash instead of a stringified object.
 */
function messageFrom(payload: Record<string, unknown> | undefined): string {
  for (const field of ["text", "message", "title"]) {
    const value = payload?.[field];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "—";
}

/** Saved items, as a short list with a link to the full page. */
export async function SavedPanel({ data }: { data: OverviewData }) {
  const t = await getTranslations("ui.account.panels");
  const items = data.saved.slice(0, 4);
  return (
    <Card className="p-3.5">
      <PanelHeading icon="🔖" title={t("saved")} href="/account/saved" action={t("savedAll")} />
      {items.length === 0 ? (
        <p className="rounded-card border border-cream-line bg-cream px-3 py-3 text-[12.5px] text-sub">
          {t("savedEmpty")}
        </p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((item, index) => (
            <li key={item.slug ?? index} className="truncate text-[13px] text-ink">
              <span aria-hidden="true" className="mr-1.5 text-muted">
                ·
              </span>
              {pickTitle(item)}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function pickTitle(item: { title?: unknown }): string {
  const title = item.title;
  if (typeof title === "string") return title;
  if (title && typeof title === "object") {
    const map = title as Record<string, string>;
    return map.en ?? Object.values(map)[0] ?? "—";
  }
  return "—";
}

/**
 * Crops and farm — a READ view over the identity profile (CP0 §3.3).
 *
 * Crops are `Profile.interests` and the farm is `FarmProfile`; both live on
 * AgriID because there is one farm and three sites read it. Nothing here is
 * editable, and the link leaves for id.agri.in. The A5 reference draws this
 * panel with a "Soon" badge, which stopped being true when ID-U1 shipped.
 */
export async function CropsPanel({
  identity,
  idOrigin,
}: {
  identity: AccountIdentity;
  idOrigin: string;
}) {
  const t = await getTranslations("ui.account.panels");
  const farm = identity.farm;
  const facts = farm
    ? [
        farm.land_area ? { label: t("farmLand"), value: `${farm.land_area} ${farm.land_unit ?? ""}`.trim() } : null,
        farm.tenure ? { label: t("farmTenure"), value: farm.tenure } : null,
        farm.cattle !== null && farm.cattle !== undefined
          ? { label: t("farmCattle"), value: String(farm.cattle) }
          : null,
        farm.goats !== null && farm.goats !== undefined
          ? { label: t("farmGoats"), value: String(farm.goats) }
          : null,
        farm.poultry !== null && farm.poultry !== undefined
          ? { label: t("farmPoultry"), value: String(farm.poultry) }
          : null,
        farm.irrigation ? { label: t("farmIrrigation"), value: farm.irrigation } : null,
      ].filter((fact): fact is { label: string; value: string } => fact !== null)
    : [];

  return (
    <Card className="p-3.5">
      <div className="mb-2.5 flex items-center gap-2">
        <h2 className="font-display text-[15px] font-extrabold text-ink">
          <span aria-hidden="true" className="mr-1.5">
            🌾
          </span>
          {t("crops")}
        </h2>
        <span className="flex-1" />
        <a
          href={`${idOrigin.replace(/\/+$/, "")}/account`}
          className="tap-target text-[12.5px] font-semibold text-brand no-underline"
        >
          {t("cropsEdit")}
        </a>
      </div>
      {identity.interests.length === 0 ? (
        <p className="text-[12.5px] text-sub">{t("cropsEmpty")}</p>
      ) : (
        <ul className="flex flex-wrap gap-1.5">
          {identity.interests.map((crop) => (
            <li
              key={crop}
              className="rounded-pill bg-brand-soft px-2.5 py-1 text-[12px] font-semibold text-brand-deep"
            >
              {crop}
            </li>
          ))}
        </ul>
      )}
      <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 border-t border-cream-line pt-2.5">
        {facts.length === 0 ? (
          <p className="text-[12px] text-muted">{t("farmEmpty")}</p>
        ) : (
          facts.map((fact) => (
            <div key={fact.label} className="text-[12px]">
              <dt className="inline text-muted">{fact.label}: </dt>
              <dd className="inline font-semibold text-ink">{fact.value}</dd>
            </div>
          ))
        )}
      </dl>
    </Card>
  );
}
