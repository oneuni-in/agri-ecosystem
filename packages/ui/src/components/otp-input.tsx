"use client";

import type { KeyboardEvent } from "react";
import { useEffect, useRef } from "react";

import { cn } from "../lib/cn";
import { applyOtpInput } from "../lib/otp";

export interface OtpInputProps {
  value: string;
  onChange: (value: string) => void;
  onComplete?: (value: string) => void;
  label: string;
  length?: number;
  disabled?: boolean;
  error?: boolean;
  className?: string;
}

/**
 * PincodeInput-style OTP boxes (D09): the same white 16px container +
 * 18px/700 numeric type, split into single-digit auto-advance boxes.
 * Every box is a 48px-tall target (≥44px minimum, §1.5). Focus ring comes
 * from the global token rule; error state borders with --alert-line.
 */
export function OtpInput({
  value,
  onChange,
  onComplete,
  label,
  length = 6,
  disabled = false,
  error = false,
  className,
}: OtpInputProps) {
  const refs = useRef<Array<HTMLInputElement | null>>([]);
  const completed = useRef<string | null>(null);

  useEffect(() => {
    if (value.length === length && completed.current !== value) {
      completed.current = value;
      onComplete?.(value);
    } else if (value.length < length) {
      // cleared (e.g. after a wrong code): the SAME code typed again must
      // fire onComplete again
      completed.current = null;
    }
  }, [value, length, onComplete]);

  const handleInput = (index: number, raw: string) => {
    const next = applyOtpInput(value, index, raw, length);
    onChange(next.value);
    refs.current[next.focusIndex]?.focus();
  };

  const handleKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Backspace" && !value[index] && index > 0) {
      event.preventDefault();
      onChange(value.slice(0, index - 1));
      refs.current[index - 1]?.focus();
    }
  };

  return (
    <div
      role="group"
      aria-label={label}
      className={cn(
        "mx-auto flex w-fit gap-1.5 rounded-card bg-card p-1.5 shadow-pin",
        className,
      )}
    >
      {Array.from({ length }, (_, index) => (
        <input
          key={index}
          ref={(node) => {
            refs.current[index] = node;
          }}
          type="text"
          inputMode="numeric"
          autoComplete={index === 0 ? "one-time-code" : "off"}
          aria-label={`${label} ${index + 1}/${length}`}
          value={value[index] ?? ""}
          disabled={disabled}
          onChange={(event) => handleInput(index, event.target.value)}
          onKeyDown={(event) => handleKeyDown(index, event)}
          onFocus={(event) => event.target.select()}
          className={cn(
            "h-12 w-11 rounded-btn border bg-transparent text-center text-lg font-bold text-ink",
            error ? "border-alert-line" : "border-line",
            "disabled:opacity-50",
          )}
        />
      ))}
    </div>
  );
}
