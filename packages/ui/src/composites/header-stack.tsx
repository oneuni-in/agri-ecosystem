import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * Header stack: gradient header → topbar (logo+tagline · pills · coins ·
 * avatar) → searchband (or PincodeHero as children).
 */
export function HeaderStack({
  logo,
  tagline,
  location,
  right,
  children,
  className,
}: {
  logo: ReactNode;
  tagline: ReactNode;
  /** LocationPill slot, next to the logo. */
  location?: ReactNode;
  /** Right cluster: LangSwitcher · CoinsPill · Avatar. */
  right?: ReactNode;
  /** Searchband content (SearchBar) or a PincodeHero. */
  children?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("bg-header-gradient", className)}>
      <div className="mx-auto flex max-w-[1140px] flex-wrap items-center gap-3 px-4 pb-1 pt-3 text-white">
        <div className="font-display text-[22px] font-extrabold leading-tight tracking-[-0.02em]">
          {logo}
          <small className="mt-[-3px] block font-body text-[11px] font-semibold tracking-normal opacity-85">
            {tagline}
          </small>
        </div>
        {location}
        <div className="ml-auto flex items-center gap-2">{right}</div>
      </div>
      {children}
    </header>
  );
}

/** Searchband slot inside the header stack (`.searchband`). */
export function SearchBand({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mx-auto max-w-[1140px] px-4 pb-4 pt-1.5", className)}>{children}</div>;
}
