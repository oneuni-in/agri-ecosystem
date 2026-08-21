import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { DataRequestsView } from "./data-requests-view";

export default async function DataRequestsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/data-requests");
  return <DataRequestsView />;
}
