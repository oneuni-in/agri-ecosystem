import { Card, Wrap } from "@agri/ui";
import { notFound, redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { ClaimForm } from "./claim-form";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

interface BusinessDetail {
  business: {
    id: string;
    name: string;
    claimable: boolean;
  };
}

export default async function ClaimPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const user = await auth.getServerUser();
  if (!user) redirect(`/api/auth/login?next=/directory/businesses/${slug}/claim`);

  const res = await fetch(`${API}/directory/businesses/${encodeURIComponent(slug)}`, {
    cache: "no-store",
  });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`directory fetch failed: ${res.status}`);
  const detail = (await res.json()) as BusinessDetail;
  const { business } = detail;

  if (!business.claimable) {
    return (
      <main>
        <Wrap className="max-w-[720px] py-6">
          <Card className="space-y-2 p-4">
            <h1 className="font-display text-[20px] font-extrabold text-ink">
              Already claimed
            </h1>
            <p className="text-[13px] text-sub">
              {business.name} has already been claimed by another owner. If you believe this is a
              mistake, contact support.
            </p>
          </Card>
        </Wrap>
      </main>
    );
  }

  return (
    <main>
      <Wrap className="max-w-[720px] py-6">
        <ClaimForm businessId={business.id} businessName={business.name} />
      </Wrap>
    </main>
  );
}
