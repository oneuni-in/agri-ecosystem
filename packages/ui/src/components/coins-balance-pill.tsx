"use client";

import { useCallback, useEffect, useState } from "react";

import { fetchCoinsBalance } from "../lib/coins-balance";
import { CoinsPill } from "./pills";

/**
 * Polls the live AgriCoins balance: on mount, whenever the tab regains
 * visibility, and on a 60s interval. Coins are always integers.
 */
export function useCoinsBalance(endpoint = "/api/coins/balance") {
  const [balance, setBalance] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    const next = await fetchCoinsBalance(endpoint);
    setBalance(next);
  }, [endpoint]);

  useEffect(() => {
    refresh();

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") refresh();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    const id = window.setInterval(refresh, 60_000);

    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.clearInterval(id);
    };
  }, [refresh]);

  return { balance, refresh };
}

/**
 * Header AgriCoins pill wired to the live balance. Renders nothing while
 * signed-out or before the first successful load, so it never occupies
 * space in a signed-out header (reuses the existing gold `CoinsPill`).
 */
export function CoinsBalancePill({
  endpoint = "/api/coins/balance",
  className,
}: {
  endpoint?: string;
  className?: string;
}) {
  const { balance } = useCoinsBalance(endpoint);
  if (balance === null) return null;
  return <CoinsPill amount={balance.toLocaleString()} className={className} />;
}
