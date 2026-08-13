/**
 * U2 catalog contracts worth pinning:
 * - StateChip tones resolve to token pairs only (no raw colors).
 * - ConsoleField wires label→control and renders the error line with the
 *   `${id}-error` id the control's aria-describedby points at.
 * - ConsoleTable keeps explicit ARIA table roles (display:block on mobile
 *   strips the implicit ones) and repeats the column label per cell for the
 *   stacked view.
 * - consoleNavLinkClass: active pill = ink fill / active sidebar row =
 *   brand-soft (the two conventions D26/M5 set).
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  AdminDataTable,
  AdminShell,
  type AdminColumn,
  ConsoleCell,
  ConsoleField,
  ConsoleHeadCell,
  ConsoleModuleCard,
  ConsoleNavItem,
  ConsoleNavList,
  ConsoleNotice,
  ConsolePageHeader,
  ConsolePanel,
  ConsoleRow,
  ConsoleShell,
  ConsoleStatRow,
  ConsoleStatTile,
  ConsoleTable,
  consoleControlClass,
  consoleNavLinkClass,
  StateChip,
} from "./console-patterns";

describe("ConsoleShell", () => {
  const html = renderToStaticMarkup(
    <ConsoleShell
      navLabel="Business console"
      heading="Business console"
      nav={
        <ConsoleNavList>
          <ConsoleNavItem>
            <a href="#" className={consoleNavLinkClass(true)}>
              Dashboard
            </a>
          </ConsoleNavItem>
        </ConsoleNavList>
      }
    >
      <p>content</p>
    </ConsoleShell>,
  );

  it("renders one nav landmark with the given label", () => {
    expect(html).toContain('aria-label="Business console"');
    expect(html.match(/<nav/g)).toHaveLength(1);
  });

  it("matches snapshot", () => {
    expect(html).toMatchSnapshot();
  });
});

describe("consoleNavLinkClass", () => {
  it("active: ink pill on mobile, brand-soft row on sm+", () => {
    const cls = consoleNavLinkClass(true);
    expect(cls).toContain("bg-ink");
    expect(cls).toContain("sm:bg-brand-soft");
    expect(cls).toContain("min-h-[44px]");
  });

  it("inactive: line pill, transparent sidebar row", () => {
    const cls = consoleNavLinkClass(false);
    expect(cls).toContain("bg-line");
    expect(cls).toContain("sm:bg-transparent");
  });
});

describe("StateChip", () => {
  it("maps every tone to a token pair", () => {
    expect(renderToStaticMarkup(<StateChip tone="ok">Active</StateChip>)).toContain(
      "bg-verified-bg",
    );
    expect(renderToStaticMarkup(<StateChip tone="pending">Pending</StateChip>)).toContain(
      "bg-sponsored-bg",
    );
    expect(renderToStaticMarkup(<StateChip tone="alert">Suspended</StateChip>)).toContain(
      "bg-alert-bg",
    );
    expect(renderToStaticMarkup(<StateChip tone="neutral">Draft</StateChip>)).toContain(
      "bg-ghost",
    );
    expect(renderToStaticMarkup(<StateChip tone="info">Premium</StateChip>)).toContain(
      "bg-brand-soft",
    );
  });
});

describe("ConsoleField", () => {
  it("wires label to control id and error to ${id}-error", () => {
    const html = renderToStaticMarkup(
      <ConsoleField id="biz-name" label="Business name" error="Enter a name">
        <input
          id="biz-name"
          className={consoleControlClass}
          aria-invalid="true"
          aria-describedby="biz-name-error"
        />
      </ConsoleField>,
    );
    expect(html).toContain('for="biz-name"');
    expect(html).toContain('id="biz-name-error"');
    expect(html).toContain("Enter a name");
  });

  it("hint yields to error", () => {
    const html = renderToStaticMarkup(
      <ConsoleField id="pin" label="Pincode" hint="6 digits" error="Invalid pincode">
        <input id="pin" className={consoleControlClass} />
      </ConsoleField>,
    );
    expect(html).toContain("Invalid pincode");
    expect(html).not.toContain("6 digits");
  });
});

describe("ConsoleTable", () => {
  const html = renderToStaticMarkup(
    <ConsoleTable
      caption="Your listings"
      head={
        <>
          <ConsoleHeadCell>Name</ConsoleHeadCell>
          <ConsoleHeadCell>Status</ConsoleHeadCell>
        </>
      }
    >
      <ConsoleRow>
        <ConsoleCell label="Name">Sakthi Dairy Farm</ConsoleCell>
        <ConsoleCell label="Status">
          <StateChip tone="ok">Active</StateChip>
        </ConsoleCell>
      </ConsoleRow>
    </ConsoleTable>,
  );

  it("keeps explicit ARIA table roles for the stacked mobile view", () => {
    expect(html).toContain('role="table"');
    expect(html).toContain('role="columnheader"');
    expect(html).toContain('role="row"');
    expect(html).toContain('role="cell"');
  });

  it("has a screen-reader caption", () => {
    expect(html).toContain("Your listings");
    expect(html).toContain("sr-only");
  });

  it("repeats the column label inside each cell for the stacked view", () => {
    // "Name" appears in the columnheader AND as the md:hidden cell label.
    expect(html.match(/Name/g)!.length).toBeGreaterThanOrEqual(2);
    expect(html).toContain("md:hidden");
  });

  it("matches snapshot", () => {
    expect(html).toMatchSnapshot();
  });
});

describe("panels, stats, notices, module card", () => {
  it("ConsolePanel renders title + action row only when titled", () => {
    const titled = renderToStaticMarkup(
      <ConsolePanel title="Coverage" action={<a href="#">Edit</a>}>
        body
      </ConsolePanel>,
    );
    expect(titled).toContain("Coverage");
    expect(titled).toContain("Edit");
    const bare = renderToStaticMarkup(<ConsolePanel>body</ConsolePanel>);
    expect(bare).not.toContain("<h2");
  });

  it("ConsoleStatRow is a labelled group of tiles", () => {
    const html = renderToStaticMarkup(
      <ConsoleStatRow label="Last 30 days">
        <ConsoleStatTile value="124" label="Profile views" hint="last 30 days" />
      </ConsoleStatRow>,
    );
    expect(html).toContain('role="group"');
    expect(html).toContain('aria-label="Last 30 days"');
    expect(html).toContain("124");
  });

  it("ConsoleNotice tones", () => {
    expect(renderToStaticMarkup(<ConsoleNotice tone="ok">Saved</ConsoleNotice>)).toContain(
      "bg-verified-bg",
    );
    expect(renderToStaticMarkup(<ConsoleNotice tone="alert">Failed</ConsoleNotice>)).toContain(
      "bg-alert-bg",
    );
  });

  it("ConsoleModuleCard hides its icon from AT", () => {
    const html = renderToStaticMarkup(
      <ConsoleModuleCard icon="📥" title="Lead inbox" sub="2 open leads" />,
    );
    expect(html).toContain('aria-hidden="true"');
    expect(html).toContain("Lead inbox");
  });

  it("ConsolePageHeader renders h1 + optional sub", () => {
    const html = renderToStaticMarkup(
      <ConsolePageHeader title="Dashboard" sub="Sakthi Dairy Farm" />,
    );
    expect(html).toContain("<h1");
    expect(html).toContain("Sakthi Dairy Farm");
  });
});

/* ── U3 admin contracts worth pinning ─────────────────────────────────────
 * - AdminShell: one nav landmark, wider frame than ConsoleShell, aside slot
 *   for the signed-in-as line; role gating happens before render (the demo
 *   and web-admin pass pre-filtered items), so there is nothing role-shaped
 *   here to test — that check lives in the app.
 * - AdminDataTable: typed columns render header+cell; hideBelow emits the
 *   FULL Tailwind literal; empty state is EmptyState (success register);
 *   error renders the alert notice; loading is a role=status skeleton; a
 *   null cursor renders no pagination control.
 */

describe("AdminShell", () => {
  const html = renderToStaticMarkup(
    <AdminShell
      navLabel="Admin console"
      heading="Admin console"
      nav={
        <ConsoleNavList>
          <ConsoleNavItem>
            <a href="#" aria-current="page" className={consoleNavLinkClass(true)}>
              Ops
            </a>
          </ConsoleNavItem>
        </ConsoleNavList>
      }
      aside={<p>Signed in as chan</p>}
    >
      <p>content</p>
    </AdminShell>,
  );

  it("renders one labelled nav landmark with the active link aria-current", () => {
    expect(html.match(/<nav/g)).toHaveLength(1);
    expect(html).toContain('aria-label="Admin console"');
    expect(html).toContain('aria-current="page"');
  });

  it("is the wide operator frame with the sidebar aside slot", () => {
    expect(html).toContain("max-w-7xl");
    expect(html).toContain("sm:w-52");
    expect(html).toContain("Signed in as chan");
  });

  it("matches snapshot", () => {
    expect(html).toMatchSnapshot();
  });
});

describe("AdminDataTable", () => {
  interface Row {
    id: string;
    name: string;
    pincode: string;
    status: string;
  }
  const columns: readonly AdminColumn<Row>[] = [
    { key: "name", header: "Business", cell: (row) => row.name },
    { key: "pincode", header: "Pincode", cell: (row) => row.pincode, hideBelow: "lg" },
    { key: "status", header: "Status", cell: (row) => <StateChip tone="ok">{row.status}</StateChip> },
  ];
  const rows: readonly Row[] = [
    { id: "r1", name: "Sakthi Dairy Farm", pincode: "641001", status: "Active" },
    { id: "r2", name: "Ponni Milk Depot", pincode: "600001", status: "Active" },
  ];
  const empty = {
    icon: "✅",
    title: "Queue clear.",
    description: "Nothing waiting for review.",
  };

  it("renders typed columns with ARIA table roles and hideBelow literals", () => {
    const html = renderToStaticMarkup(
      <AdminDataTable
        caption="Businesses"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        empty={empty}
      />,
    );
    expect(html).toContain('role="table"');
    expect(html).toContain('role="columnheader"');
    expect(html).toContain("Sakthi Dairy Farm");
    // The full Tailwind literal, on the header and on each body cell.
    expect(html.match(/max-lg:hidden/g)!.length).toBeGreaterThanOrEqual(3);
  });

  it("renders the toolbar slot above the table", () => {
    const html = renderToStaticMarkup(
      <AdminDataTable
        caption="Businesses"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        empty={empty}
        toolbar={<input aria-label="Search businesses" />}
      />,
    );
    expect(html).toContain('aria-label="Search businesses"');
  });

  it("empty state reads as success via EmptyState, not error", () => {
    const html = renderToStaticMarkup(
      <AdminDataTable
        caption="Businesses"
        columns={columns}
        rows={[]}
        rowKey={(row: Row) => row.id}
        empty={empty}
      />,
    );
    expect(html).toContain("Queue clear.");
    expect(html).not.toContain('role="table"');
    expect(html).not.toContain("bg-alert-bg");
  });

  it("error renders the alert notice with the retry slot", () => {
    const html = renderToStaticMarkup(
      <AdminDataTable
        caption="Businesses"
        columns={columns}
        rows={[]}
        rowKey={(row: Row) => row.id}
        empty={empty}
        error="Could not load businesses."
        errorAction={<button>Retry</button>}
      />,
    );
    expect(html).toContain("bg-alert-bg");
    expect(html).toContain("Could not load businesses.");
    expect(html).toContain("Retry");
  });

  it("loading is an sr-labelled status skeleton", () => {
    const html = renderToStaticMarkup(
      <AdminDataTable
        caption="Businesses"
        columns={columns}
        rows={[]}
        rowKey={(row: Row) => row.id}
        empty={empty}
        loading
      />,
    );
    expect(html).toContain('role="status"');
    expect(html).toContain("Loading");
    expect(html).not.toContain("Queue clear.");
  });

  it("a null cursor renders no pagination control", () => {
    const html = renderToStaticMarkup(
      <AdminDataTable
        caption="Businesses"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        empty={empty}
        nextCursor={null}
        onLoadMore={() => {}}
      />,
    );
    expect(html).not.toContain("Load more");
  });

  it("an opaque cursor renders the load-more control", () => {
    const html = renderToStaticMarkup(
      <AdminDataTable
        caption="Businesses"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        empty={empty}
        nextCursor="opaque-cursor"
        onLoadMore={() => {}}
      />,
    );
    expect(html).toContain("Load more");
  });

  it("row open renders a real focusable button per row with its label", () => {
    const html = renderToStaticMarkup(
      <AdminDataTable
        caption="Businesses"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        empty={empty}
        onRowOpen={() => {}}
        rowOpenLabel={(row) => `Open ${row.name}`}
      />,
    );
    expect(html).toContain('aria-label="Open Sakthi Dairy Farm"');
    expect(html.match(/<button/g)!.length).toBeGreaterThanOrEqual(2);
    expect(html).toContain("cursor-pointer");
  });

  it("matches snapshot", () => {
    const html = renderToStaticMarkup(
      <AdminDataTable
        caption="Businesses"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        empty={empty}
      />,
    );
    expect(html).toMatchSnapshot();
  });
});
