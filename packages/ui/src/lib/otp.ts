/**
 * Pure OTP-box state transition: given the current value, the box index the
 * user typed into, and the raw input (a keystroke or a paste), return the
 * next value and which box should hold focus. Kept out of the component so
 * the auto-advance/paste rules are unit-testable without a DOM.
 */
export function applyOtpInput(
  current: string,
  index: number,
  raw: string,
  length: number,
): { value: string; focusIndex: number } {
  const digits = raw.replace(/\D/g, "");
  if (!digits) return { value: current, focusIndex: index };
  // a full code pasted anywhere fills every box from the start
  if (digits.length >= length) {
    return { value: digits.slice(0, length), focusIndex: length - 1 };
  }
  const chars = current.padEnd(index, " ").split("");
  let cursor = index;
  for (const digit of digits) {
    if (cursor >= length) break;
    chars[cursor] = digit;
    cursor += 1;
  }
  const value = chars.join("").replace(/\s+$/, "").slice(0, length);
  return { value, focusIndex: Math.min(cursor, length - 1) };
}
