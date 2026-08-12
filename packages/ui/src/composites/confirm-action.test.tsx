/**
 * ConfirmAction is a client island; SSR renders the trigger only. The
 * two-step contract (nothing mutates until the in-dialog confirm) is
 * exercised end-to-end by the console e2e once Group B wires deletes —
 * here we pin the closed-by-default shape.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Button } from "../components/button";
import { ConfirmAction } from "./confirm-action";

describe("ConfirmAction", () => {
  const html = renderToStaticMarkup(
    <ConfirmAction
      trigger={<Button variant="ghost">Delete listing</Button>}
      title="Delete this listing?"
      description="It is hidden from public results immediately. Admins can restore it."
      confirmLabel="Delete listing"
      cancelLabel="Keep it"
      onConfirm={() => {}}
    />,
  );

  it("renders the trigger, closed by default", () => {
    expect(html).toContain("Delete listing");
    expect(html).not.toContain("Keep it"); // dialog content only mounts open
  });
});
