/** Atom: primary label with an optional vernacular second line. `vern`
 * carries the `.vern` class the design system uses for Tamil/Hindi copy. */
export function Label({ en, vern }: { en: string; vern?: string }) {
  return (
    <span className="flex flex-col items-center gap-0.5 text-center">
      <span className="text-[12px] font-bold leading-tight text-ink">{en}</span>
      {vern ? <span className="vern text-[11px] leading-tight text-sub">{vern}</span> : null}
    </span>
  );
}
