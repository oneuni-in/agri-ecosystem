import { describe, expect, it } from "vitest";

import { decideInstallSurface, isIosUserAgent } from "./install-prompt";

/**
 * AG-A66: the §19 band's "no dead button ever" contract, as a truth table.
 * Every combination of the three browser facts maps to exactly one surface.
 */
describe("decideInstallSurface", () => {
  it.each([
    // standalone wins over everything: already installed → never ask.
    [{ hasPrompt: false, isIOS: false, isStandalone: true }, "absent"],
    [{ hasPrompt: true, isIOS: false, isStandalone: true }, "absent"],
    [{ hasPrompt: false, isIOS: true, isStandalone: true }, "absent"],
    [{ hasPrompt: true, isIOS: true, isStandalone: true }, "absent"],
    // a held beforeinstallprompt → the button genuinely works.
    [{ hasPrompt: true, isIOS: false, isStandalone: false }, "button"],
    // ...even when the UA sniff says iOS: a browser that PROVED it can
    // prompt outranks a string that claims it cannot.
    [{ hasPrompt: true, isIOS: true, isStandalone: false }, "button"],
    // iOS Safari never fires the event → instruction variant, never a button.
    [{ hasPrompt: false, isIOS: true, isStandalone: false }, "ios"],
    // no event, not iOS (unsupported / desktop-installed) → nothing at all.
    [{ hasPrompt: false, isIOS: false, isStandalone: false }, "absent"],
  ] as const)("%o → %s", (flags, surface) => {
    expect(decideInstallSurface(flags)).toBe(surface);
  });
});

describe("isIosUserAgent (same sniff as lib/push.ts's ios-install state)", () => {
  it.each([
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1", true],
    ["Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1", true],
    ["Mozilla/5.0 (iPod touch; CPU iPhone OS 15_8 like Mac OS X) AppleWebKit/605.1.15", true],
    ["Mozilla/5.0 (Linux; Android 14; SM-A356E) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36", false],
    ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36", false],
    // Known, accepted gap (also push.ts's): iPadOS desktop-mode reports a
    // Macintosh UA → resolves to "absent" — an absent band, never a dead one.
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15", false],
  ])("%s → %s", (ua, expected) => {
    expect(isIosUserAgent(ua)).toBe(expected);
  });
});
