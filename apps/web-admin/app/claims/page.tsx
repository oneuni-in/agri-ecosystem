import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { ClaimsManager } from "./claims-manager";

export default async function ClaimsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/claims");
  return <ClaimsManager />;
}
