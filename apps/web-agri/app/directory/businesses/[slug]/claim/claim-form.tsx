"use client";

import { Button, Card } from "@agri/ui";
import { useState } from "react";

const MAX_FILES = 5;
const ACCEPTED_TYPES = "image/jpeg,image/png,image/webp";

type SubmitState = "idle" | "submitting" | "done";

function AlertNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

export function ClaimForm({
  businessId,
  businessName,
}: {
  businessId: string;
  businessName: string;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [state, setState] = useState<SubmitState>("idle");
  const [error, setError] = useState<string | null>(null);

  const submitting = state === "submitting";

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (files.length < 1 || files.length > MAX_FILES) {
      setError(`Attach between 1 and ${MAX_FILES} photos.`);
      return;
    }
    setState("submitting");
    setError(null);
    const form = new FormData();
    for (const file of files) form.append("files", file);
    try {
      const res = await fetch(`/api/directory/businesses/${businessId}/claim`, {
        method: "POST",
        body: form,
      });
      if (res.status === 201) {
        setState("done");
        return;
      }
      const body = (await res.json().catch(() => null)) as { detail?: string } | null;
      if (res.status === 409) {
        setError(
          body?.detail === "claim_pending"
            ? "You already have a pending claim for this listing."
            : "This listing has already been claimed by someone else.",
        );
      } else {
        setError(body?.detail ?? "Something went wrong. Please try again.");
      }
      setState("idle");
    } catch {
      setError("Something went wrong. Please try again.");
      setState("idle");
    }
  };

  if (state === "done") {
    return (
      <Card className="space-y-2 p-4">
        <h1 className="font-display text-[20px] font-extrabold text-ink">Claim submitted</h1>
        <p className="text-[13px] text-sub">
          Your claim for {businessName} is pending review. We&apos;ll notify you once it&apos;s
          decided.
        </p>
      </Card>
    );
  }

  return (
    <Card className="space-y-3 p-4">
      <header className="space-y-1">
        <h1 className="font-display text-[20px] font-extrabold text-ink">
          Claim {businessName}
        </h1>
        <p className="text-[13px] text-sub">
          Upload 1-{MAX_FILES} photos proving you run this business (shopfront, GST certificate, a
          bill with the business name). Photos are re-encoded server-side and location metadata is
          removed.
        </p>
      </header>
      <form className="space-y-3" onSubmit={(event) => void submit(event)}>
        <label className="block text-[13px] font-semibold text-ink">
          Evidence photos
          <input
            type="file"
            accept={ACCEPTED_TYPES}
            multiple
            className="mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink"
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
          />
        </label>
        {error ? <AlertNotice>{error}</AlertNotice> : null}
        <Button type="submit" variant="brand" disabled={submitting} className="max-w-[240px]">
          {submitting ? "Submitting..." : "Submit claim"}
        </Button>
      </form>
    </Card>
  );
}
