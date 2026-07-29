/** Atom: a decorative glyph. `aria-hidden` because the adjacent Label
 * already carries the accessible name — announcing both would read the
 * category twice. */
export function Icon({ glyph }: { glyph: string }) {
  return (
    <span aria-hidden="true" className="text-[26px] leading-none">
      {glyph}
    </span>
  );
}
