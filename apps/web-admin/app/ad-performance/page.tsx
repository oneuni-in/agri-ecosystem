import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { AdPerformanceView } from "./ad-performance-view";

export default async function AdPerformancePage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/ad-performance");
  return <AdPerformanceView />;
}
