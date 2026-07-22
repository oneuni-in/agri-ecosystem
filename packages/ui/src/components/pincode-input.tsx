import type { InputHTMLAttributes } from "react";

import { cn } from "../lib/cn";

export interface PincodeInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "inputMode" | "maxLength"> {
  findLabel: string;
  className?: string;
  /** Click handler for the "Find" button. When omitted the button stays inert
   * (legacy behaviour: some callers resolve via a separate submit button). */
  onFind?: () => void;
  /** Disable the "Find" button independently of the input. */
  findDisabled?: boolean;
}

/**
 * Pincode is the universal control — location does the filtering (UX law 6).
 * White 16px container, 18px/700 numeric input with .15em tracking, solid
 * brand "Find" button (`.pinbox`).
 */
export function PincodeInput({
  findLabel,
  className,
  onFind,
  findDisabled,
  ...inputProps
}: PincodeInputProps) {
  return (
    <div
      className={cn(
        "mx-auto flex w-full max-w-[520px] gap-1.5 rounded-card bg-card p-1.5 shadow-pin",
        className,
      )}
    >
      <input
        type="text"
        inputMode="numeric"
        maxLength={6}
        pattern="[0-9]*"
        className="min-w-0 flex-1 border-none bg-transparent px-3.5 py-3 text-lg font-bold tracking-[.15em] text-ink placeholder:text-sub focus:outline-none"
        {...inputProps}
      />
      <button
        type="button"
        onClick={onFind}
        disabled={findDisabled}
        className="min-h-[44px] rounded-btn bg-brand px-[22px] text-[15px] font-extrabold text-white disabled:opacity-50"
      >
        {findLabel}
      </button>
    </div>
  );
}
