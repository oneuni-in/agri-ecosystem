/**
 * Server half of the shell: reads the session, filters the module catalog by
 * the operator's roles, and only then mounts `AdminShell`. A non-admin
 * session cannot render the admin nav twice over — the BFF never mints a
 * session below staff (lib/auth.ts `requiredRoles`), and a null/roleless
 * user yields zero items here, so the children render bare with no shell.
 */
import { AdminShell } from "@agri/ui";
import type { ReactNode } from "react";

import { auth } from "@/lib/auth";

import { AdminNav } from "./admin-nav";
import { navFor } from "./nav-items";

export async function AdminChrome({ children }: { children: ReactNode }) {
  const user = await auth.getServerUser();
  const items = user ? navFor(user.roles) : [];
  if (items.length === 0) return <>{children}</>;
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
