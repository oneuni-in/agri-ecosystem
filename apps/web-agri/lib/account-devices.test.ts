import { describe, expect, it } from "vitest";

import { deviceIcon, groupDevices, siteLabelKey, type Device } from "./account-devices";

/**
 * AG-U5 P5 — the read-only device rows.
 *
 * ID-U1 recorded the trap these guard: next-intl's `t()` has no fallback and
 * THROWS on a missing key, so a session belonging to an OAuth client this
 * build has never heard of would take the whole row down with it.
 */
describe("siteLabelKey", () => {
  it("names the sites the catalogue knows", () => {
    expect(siteLabelKey("web-agri")).toBe("sites.web-agri");
    expect(siteLabelKey("web-milk")).toBe("sites.web-milk");
    expect(siteLabelKey("web")).toBe("sites.web");
  });

  it("returns null for a client the catalogue has never heard of", () => {
    // A client_id registered after this build ships must render as itself,
    // not throw. null is the caller's signal to print the raw kind.
    expect(siteLabelKey("web-future-vertical")).toBe(null);
    expect(siteLabelKey("")).toBe(null);
  });
});

function device(over: Partial<Device> & Pick<Device, "device_id" | "kind">): Device {
  return {
    label: null,
    current: false,
    created_at: "2026-08-01T00:00:00Z",
    last_seen_at: null,
    device_kind: null,
    place: null,
    device_group: null,
    ...over,
  };
}

describe("groupDevices", () => {
  it("folds one browser's web session and app sessions into a single device", () => {
    const groups = groupDevices([
      device({ device_id: "1", kind: "web", device_group: "fp-a", current: true }),
      device({ device_id: "2", kind: "web-agri", device_group: "fp-a" }),
      device({ device_id: "3", kind: "web-admin", device_group: "fp-a" }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0]?.sites).toEqual(["web", "web-agri", "web-admin"]);
    expect(groups[0]?.current).toBe(true);
    expect(groups[0]?.rows).toHaveLength(3);
  });

  it("keeps genuinely different devices apart", () => {
    const groups = groupDevices([
      device({ device_id: "1", kind: "web", device_group: "fp-a" }),
      device({ device_id: "2", kind: "web", device_group: "fp-b" }),
    ]);
    expect(groups).toHaveLength(2);
  });

  it("never merges rows that recorded no fingerprint", () => {
    // null is "we do not know", not "the same unknown machine"
    const groups = groupDevices([
      device({ device_id: "1", kind: "web" }),
      device({ device_id: "2", kind: "web" }),
    ]);
    expect(groups).toHaveLength(2);
  });

  it("reports the newest activity and the first name anyone gave the device", () => {
    const groups = groupDevices([
      device({
        device_id: "1",
        kind: "web",
        device_group: "fp-a",
        last_seen_at: "2026-08-01T00:00:00Z",
      }),
      device({
        device_id: "2",
        kind: "web-agri",
        device_group: "fp-a",
        label: "Work laptop",
        device_kind: "Windows - Chrome",
        last_seen_at: "2026-08-20T00:00:00Z",
      }),
    ]);
    expect(groups[0]?.label).toBe("Work laptop");
    expect(groups[0]?.deviceKind).toBe("Windows - Chrome");
    expect(groups[0]?.activeAt).toBe(new Date("2026-08-20T00:00:00Z").getTime());
  });

  it("falls back to created_at when a row was never seen again", () => {
    const groups = groupDevices([
      device({ device_id: "1", kind: "web", device_group: "fp-a", created_at: "2026-07-04T00:00:00Z" }),
    ]);
    expect(groups[0]?.activeAt).toBe(new Date("2026-07-04T00:00:00Z").getTime());
  });
});

describe("deviceIcon", () => {
  it("tells a phone from a computer", () => {
    expect(deviceIcon("Android 14")).toBe("📱");
    expect(deviceIcon("Windows 11")).toBe("💻");
  });

  it("marks an installed app differently from a browser", () => {
    expect(deviceIcon("Installed app · Android")).toBe("📲");
  });

  it("falls back to a computer when the device is unknown", () => {
    expect(deviceIcon(null)).toBe("💻");
    expect(deviceIcon("Weird New OS")).toBe("💻");
  });
});
