import Link from "next/link";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";
import { CONSOLE_MODULES } from "@/lib/console-modules";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** billing_enabled probe: the backend 404s the whole /billing surface while
 * dark, so one status check lights (or hides) the billing module. */
async function billingVisible(): Promise<boolean> {
  const token = await auth.getAccessToken();
  if (!token) return false;
  try {
    const response = await fetch(`${API}/billing/subscription`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    return response.status !== 404;
  } catch {
    return false;
  }
}

export default async function BusinessConsoleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business");
  const showBilling = await billingVisible();
  const modules = CONSOLE_MODULES.filter((entry) =>
    entry.gate === "billing" ? showBilling : true,
  );
  return (
    <div className="mx-auto flex w-full max-w-5xl gap-6 px-4 py-6">
      <nav aria-label="Business console" className="w-48 shrink-0">
        <p className="mb-3 font-display text-[13px] font-extrabold uppercase tracking-wide text-sub">
          Business console
        </p>
        <ul className="space-y-1">
          {modules.map((entry) => (
            <li key={entry.id}>
              <Link
                href={entry.href}
                className="block rounded-card px-3 py-2 text-[14px] text-ink hover:bg-line"
              >
                {entry.title}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
