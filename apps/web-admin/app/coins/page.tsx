import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { CoinsAdmin } from "./coins-admin";

export default async function CoinsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/coins");
  return <CoinsAdmin />;
}
