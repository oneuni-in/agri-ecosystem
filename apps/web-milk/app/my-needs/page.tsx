import type { Metadata } from "next";

import { MyNeedsClient } from "./my-needs-client";

// Private per-user page: noindex, client-fetched through the auth BFF.
export const metadata: Metadata = {
  title: "My needs — Milk.in",
  robots: { index: false },
};

export default function MyNeedsPage() {
  return (
    <main className="mx-auto max-w-[720px] space-y-4 px-4 py-6">
      <h1 className="font-display text-[22px] font-extrabold text-ink">
        My needs <span className="vern font-normal">· என் தேவைகள்</span>
      </h1>
      <MyNeedsClient />
    </main>
  );
}
