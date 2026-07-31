import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { BusinessesManager } from "./businesses-manager";

export default async function BusinessesPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/businesses");
  return <BusinessesManager />;
}
