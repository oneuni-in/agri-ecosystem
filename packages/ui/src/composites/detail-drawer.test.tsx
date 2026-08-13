/**
 * DetailDrawer is a CONTROLLED client island (the opener is a table row, not
 * an in-tree trigger); its portal content mounts client-side only. SSR of the
 * closed drawer must render nothing — that IS the contract worth pinning
 * here: no stray landmark, no hidden content, nothing for AT to trip on.
 * Open/close/focus behaviour is Radix's and is exercised by the admin e2e.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DetailDrawer } from "./detail-drawer";

describe("DetailDrawer", () => {
  it("closed: renders nothing at all", () => {
    const html = renderToStaticMarkup(
      <DetailDrawer open={false} onOpenChange={() => {}} title="Sakthi Dairy Farm">
        <p>detail body</p>
      </DetailDrawer>,
    );
    expect(html).toBe("");
  });
});
