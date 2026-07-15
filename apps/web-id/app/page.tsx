import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** Landing: signed-in users manage devices, everyone else signs in. */
export default async function Home() {
  const jar = await cookies();
  const sid = jar.get("agri_sid")?.value;
  if (sid) {
    const me = await fetch(`${API}/auth/me`, {
      headers: { cookie: `agri_sid=${sid}` },
      cache: "no-store",
    });
    if (me.ok) redirect("/devices");
  }
  redirect("/login");
}
