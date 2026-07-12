import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { UsersManager } from "./users-manager";

export default async function UsersPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/users");
  return <UsersManager />;
}
