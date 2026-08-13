import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { TiersView } from "./tiers-view";

export default async function TiersPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/tiers");
  return <TiersView />;
}
