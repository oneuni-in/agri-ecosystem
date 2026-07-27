"use client";

/**
 * Client wrapper around the dumb `SearchBar` (D19 Task 8/10). `SearchBar`
 * has no `onSearch`/state of its own — it is a plain input + decorative
 * mic/cam buttons. Wiring it to the search API is just a native GET form:
 * submitting navigates to `/search?q=...`, which the server component in
 * `page.tsx` reads via `searchParams`. No client-side fetch, no JS required
 * for the happy path.
 *
 * This page sits below the global `SiteHeader` (no header gradient), so
 * unlike the home page's `SearchBand` usage we skip `hint`/`showCam` —
 * those are styled for the white/85-on-gradient look and would be out of
 * place on a plain content page (mockup has no dedicated /search screen;
 * `.searchbox` itself is reused, the gradient chrome around it is not).
 */
import { SearchBar } from "@agri/ui";

export function SearchForm({
  initialQ,
  placeholder,
  inputLabel,
  micLabel,
}: {
  initialQ: string;
  placeholder: string;
  inputLabel: string;
  micLabel: string;
}) {
  return (
    <form action="/search" method="get" role="search">
      <SearchBar
        name="q"
        defaultValue={initialQ}
        placeholder={placeholder}
        aria-label={inputLabel}
        micLabel={micLabel}
      />
    </form>
  );
}
