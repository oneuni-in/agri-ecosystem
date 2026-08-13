import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { PaymentsView } from "./payments-view";

export default async function PaymentsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/payments");
  return <PaymentsView />;
}
