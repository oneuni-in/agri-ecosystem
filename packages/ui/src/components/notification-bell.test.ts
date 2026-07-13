import { describe, expect, it } from "vitest";

import { formatUnread } from "./notification-bell";

describe("formatUnread", () => {
  it("hides zero, shows counts, caps at 99+", () => {
    expect(formatUnread(0)).toBe("");
    expect(formatUnread(-3)).toBe("");
    expect(formatUnread(1)).toBe("1");
    expect(formatUnread(99)).toBe("99");
    expect(formatUnread(140)).toBe("99+");
  });
});
