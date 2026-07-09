"use client";

import * as RadixToast from "@radix-ui/react-toast";
import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";

import { cn } from "../lib/cn";

interface ToastOptions {
  title: ReactNode;
  description?: ReactNode;
}

const ToastContext = createContext<{ toast: (opts: ToastOptions) => void } | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}

/** Client island. Wrap interactive subtrees that need transient feedback. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<(ToastOptions & { id: number })[]>([]);

  const toast = useCallback((opts: ToastOptions) => {
    setItems((prev) => [...prev, { ...opts, id: prev.length + 1 }]);
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      <RadixToast.Provider swipeDirection="right" duration={4000}>
        {children}
        {items.map((item) => (
          <RadixToast.Root
            key={item.id}
            className={cn(
              "flex flex-col gap-0.5 rounded-card border border-line bg-card p-4 shadow-search",
            )}
          >
            <RadixToast.Title className="text-[14px] font-extrabold">
              {item.title}
            </RadixToast.Title>
            {item.description ? (
              <RadixToast.Description className="text-[12.5px] text-sub">
                {item.description}
              </RadixToast.Description>
            ) : null}
          </RadixToast.Root>
        ))}
        <RadixToast.Viewport className="fixed bottom-20 right-4 z-[100] flex w-[300px] max-w-[calc(100vw-32px)] flex-col gap-2" />
      </RadixToast.Provider>
    </ToastContext.Provider>
  );
}
