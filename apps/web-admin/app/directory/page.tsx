import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { DirectoryBrowse } from "./directory-browse";

export default async function DirectoryPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/directory");
  return <DirectoryBrowse />;
}
