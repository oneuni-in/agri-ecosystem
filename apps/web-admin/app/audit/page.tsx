import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { AuditView } from "./audit-view";

export default async function AuditPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/audit");
  return <AuditView />;
}
