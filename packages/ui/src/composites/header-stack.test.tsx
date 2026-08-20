/**
 * HeaderStack's `logo` slot accepts either plain text or a link node
 * (AG-A64). The package is routing-free, so the apps pass their own
 * `<Link href="/">` — here a plain `<a>` stands in for it — and on the home
 * page they pass plain text instead (no self-link). Both shapes must render
 * inside the wordmark span without the slot mangling the markup.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { HeaderStack } from "./header-stack";

describe("HeaderStack logo slot", () => {
  it("renders a link node when given one (non-home pages)", () => {
    const html = renderToStaticMarkup(
      <HeaderStack
        logo={
          <a href="/" className="tap-target text-inherit no-underline">
            agri.in
          </a>
        }
        tagline="Farmers first"
      />,
    );
    expect(html).toContain('<a href="/"');
    expect(html).toContain("agri.in");
    // The anchor stays nested inside the wordmark span so it inherits the
    // brand typography (span > a is valid phrasing content).
    expect(html).toMatch(/<span[^>]*>\s*<a href="\/"/);
  });

  it("renders plain text when given a string (home page)", () => {
    const html = renderToStaticMarkup(<HeaderStack logo="agri.in" tagline="Farmers first" />);
    expect(html).toContain("agri.in");
    expect(html).not.toContain("<a ");
  });
});
