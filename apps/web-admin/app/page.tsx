/**
 * Console home: the same role-filtered module catalog the shell nav renders
 * from (nav-items.ts), as dashboard entry tiles. Anonymous / non-admin
 * visitors get a sign-in panel — the header's AuthCluster runs the SSO dance,
 * and the BFF refuses to mint a session below staff.
 */
import { ConsoleModuleCard, ConsolePageHeader, EmptyState } from "@agri/ui";
import Link from "next/link";

import { auth } from "@/lib/auth";

import { navFor } from "./nav-items";

export default async function Page() {
  const user = await auth.getServerUser();
  const modules = (user ? navFor(user.roles) : []).filter((item) => item.href !== "/");

  if (modules.length === 0) {
    return (
      <main className="mx-auto w-full max-w-md px-4 py-16">
        <EmptyState
          icon="🔐"
          title="Staff sign-in required."
          description="Use Login in the header with your staff AgriID. Sessions below staff are refused."
        />
      </main>
    );
  }

  return (
    <main>
      <ConsolePageHeader title="Dashboard" sub="Milk.in operations console" />
      <div className="grid gap-2.5 md:grid-cols-2 lg:grid-cols-3">
        {modules.map((item) => (
          <Link key={item.href} href={item.href} className="no-underline">
            <ConsoleModuleCard icon={item.icon} title={item.title} sub={item.sub} />
          </Link>
        ))}
      </div>
    </main>
  );
}
