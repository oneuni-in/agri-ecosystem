/**
 * Pure, framework-free balance fetcher for the AgriCoins header pill.
 *
 * `fetchImpl` is injectable so it can be tested with a fake in a plain
 * `node` vitest environment (no jsdom, no real network).
 */
export async function fetchCoinsBalance(
  endpoint = "/api/coins/balance",
  fetchImpl: typeof fetch = fetch,
): Promise<number | null> {
  try {
    const res = await fetchImpl(endpoint, { credentials: "include" });
    if (res.status === 401) return null; // signed out
    if (!res.ok) return null; // transient
    const body = (await res.json()) as { balance?: unknown };
    return typeof body.balance === "number" ? body.balance : null;
  } catch {
    return null; // network blip
  }
}
