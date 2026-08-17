import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { ContentManager } from "./content-manager";

/** Private staff console page - never indexed. */
export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

export default async function ContentPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/content");
  return <ContentManager />;
}
