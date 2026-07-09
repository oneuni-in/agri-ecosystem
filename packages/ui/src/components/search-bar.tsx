import type { InputHTMLAttributes, ReactNode } from "react";

export interface SearchBarProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Hint line rendered below the bar in white/85 — sits on the header gradient. */
  hint?: ReactNode;
  /** Optional camera slot (photo search) between input and mic. */
  showCam?: boolean;
  micLabel: string;
  camLabel?: string;
}

/**
 * Floating white search bar (`.searchbox`): 46px accent mic is right-most
 * — voice is first-class (UX law 3).
 */
export function SearchBar({
  hint,
  showCam = false,
  micLabel,
  camLabel = "Search by photo",
  className,
  ...inputProps
}: SearchBarProps) {
  return (
    <div className={className}>
      <div className="flex items-center gap-2.5 rounded-card bg-card py-1.5 pl-[18px] pr-1.5 shadow-search">
        <span aria-hidden="true" className="text-lg">
          🔍
        </span>
        <input
          type="text"
          className="min-w-0 flex-1 border-none bg-transparent py-3 text-base text-ink placeholder:text-sub focus:outline-none"
          {...inputProps}
        />
        {showCam ? (
          <button
            type="button"
            aria-label={camLabel}
            className="flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-btn bg-ghost text-xl"
          >
            📷
          </button>
        ) : null}
        <button
          type="button"
          aria-label={micLabel}
          className="flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-btn bg-accent text-xl text-white"
        >
          🎤
        </button>
      </div>
      {hint ? (
        <div className="mt-2 px-1 text-[12.5px] font-medium text-white/85">{hint}</div>
      ) : null}
    </div>
  );
}
