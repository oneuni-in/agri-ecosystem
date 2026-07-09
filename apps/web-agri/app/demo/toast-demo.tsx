"use client";

import { Button, ToastProvider, useToast } from "@agri/ui";

function Trigger() {
  const { toast } = useToast();
  return (
    <Button
      variant="brand"
      className="max-w-[220px]"
      onClick={() =>
        toast({ title: "Listing saved", description: "We will notify vendors in 641001." })
      }
    >
      Show toast
    </Button>
  );
}

export function ToastDemo() {
  return (
    <ToastProvider>
      <Trigger />
    </ToastProvider>
  );
}
