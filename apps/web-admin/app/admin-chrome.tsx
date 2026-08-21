/**
 * Server half of the shell: reads the session, filters the module catalog by
 * the operator's roles, and only then mounts `AdminShell`.
 *
 * Degrades CLOSED. This used to return `children` bare when the catalog came
 * back empty — a null or roleless user got the page body with no shell, on the
 * reasoning that the BFF never mints a session below staff (lib/auth.ts
 * `requiredRoles`), so the case could not arise. That reasoning is sound and
 * still holds; it was also the only thing holding. A shell that renders its
 * contents for a user it just decided has no modules is a strange thing to
 * ship in the console that suspends accounts and assigns roles, so the empty
 * case now refuses instead. If the invariant above ever breaks, this is a
 * blank panel rather than an exposed admin page.
 */
import { AdminShell } from "@agri/ui";
import type { ReactNode } from "react";

import { auth } from "@/lib/auth";

import { AdminNav } from "./admin-nav";
import { navFor } from "./nav-items";

export async function AdminChrome({ children }: { children: ReactNode }) {
  const user = await auth.getServerUser();
  const items = user ? navFor(user.roles) : [];
  if (items.length === 0) {
    return (
      <main className="mx-auto max-w-[560px] px-4 py-16">
        <p className="text-[13px] text-muted">
          This account has no admin modules. Sign in with a staff account to continue.
        </p>
      </main>
    );
  }
  return (
    <AdminShell
      navLabel="Admin console"
      heading="Admin console"
      nav={<AdminNav items={items} />}
      aside={
        <p className="text-[11.5px] text-muted">
          Signed in as {user?.name ?? user?.agriId}
        </p>
      }
    >
      {children}
    </AdminShell>
  );
}
