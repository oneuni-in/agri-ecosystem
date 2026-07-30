import { CONSOLE_URL, listingsHref } from "@/lib/console";

/**
 * Molecule: the front door for brands. A cross-origin link to the EXISTING
 * D16 claim/create flow in the Business Console (`apps/web-agri/app/business/*`)
 * — a door, not a new flow. No new route, no new backend surface.
 *
 * Deliberately a plain <a>, not a hydrating island: `site-footer.tsx`
 * records that a fourth item in the header's right cluster moved CLS from
 * 0.098 to 0.136 as the islands populated. A static link is in the initial
 * HTML and cannot shift.
 */
export function ListBusinessCta({
  variant = "block",
}: {
  variant?: "header" | "footer" | "block";
}) {
  const className =
    variant === "block"
      ? "block rounded-card border border-line bg-card px-4 py-3 text-center text-[14px] font-bold text-ink no-underline"
      : // header/footer: same 44px tap-target floor as every other interactive
        // element in this codebase (design-system.md §1.5) — inline-flex +
        // min-h keeps the invisible hit area 44px tall without adding a
        // background/border, so it stays visually a plain text link.
        "inline-flex min-h-[44px] items-center px-1.5 text-[13px] font-bold text-ink no-underline";
  return (
    <a href={listingsHref(CONSOLE_URL)} className={className} data-testid="list-business-cta">
      List your dairy business{" "}
      <span className="vern font-normal text-sub">· உங்கள் வணிகத்தைப் பதிவு செய்யுங்கள்</span>
    </a>
  );
}
