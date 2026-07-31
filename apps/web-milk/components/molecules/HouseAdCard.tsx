import { Link } from "@/i18n/navigation";

/**
 * Molecule (M2): local house fallback for ad slots. Rendered ONLY when the ad
 * engine returns nothing (flag off / no fill / ad-blocker) so the reserved
 * box never collapses (NN3 CLS + "surfaces never empty"). First-party CTA,
 * not a served creative - so no Sponsored badge and no tracking beacons.
 * External hrefs (the cross-origin Business Console) get a plain <a>;
 * internal paths go through the locale-aware Link.
 */
export function HouseAdCard({
  title,
  vern,
  href,
}: {
  title: string;
  vern?: string;
  href: string;
}) {
  const className =
    "flex h-full w-full flex-col items-center justify-center gap-0.5 rounded-card border border-line bg-brand-soft px-4 text-center no-underline";
  const body = (
    <>
      <span className="text-[14px] font-extrabold leading-tight text-ink">{title}</span>
      {vern ? <span className="vern text-[12px] leading-tight text-sub">{vern}</span> : null}
    </>
  );
  if (href.startsWith("http")) {
    return (
      <a href={href} className={className} data-testid="house-ad-fallback">
        {body}
      </a>
    );
  }
  return (
    <Link href={href} prefetch={false} className={className} data-testid="house-ad-fallback">
      {body}
    </Link>
  );
}
