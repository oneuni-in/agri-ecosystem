import { getMessages } from "next-intl/server";

/**
 * AG-A8 payload discipline: the root layout ships ONLY the ui namespaces
 * that client islands on PUBLIC pages use. Route groups with their own
 * client vocabulary (/business console, /tools, /c/[slug]) nest a second
 * NextIntlClientProvider via this helper — a nested provider REPLACES
 * messages for its subtree, so each route pays for its own catalog and the
 * home's flight payload stays lean (shipping the whole console catalog on
 * `/` measurably moved the Lighthouse median). Server components always
 * read the full catalog regardless.
 */
export async function pickUiMessages(
  namespaces: readonly string[],
): Promise<Record<string, unknown>> {
  const all = await getMessages();
  const ui = (all.ui ?? {}) as Record<string, unknown>;
  const picked: Record<string, unknown> = {};
  for (const path of namespaces) {
    const keys = path.split(".");
    let src: unknown = ui;
    for (const k of keys) src = (src as Record<string, unknown> | undefined)?.[k];
    if (src === undefined) continue;
    let dst = picked;
    for (const k of keys.slice(0, -1)) {
      dst[k] = dst[k] ?? {};
      dst = dst[k] as Record<string, unknown>;
    }
    dst[keys[keys.length - 1] as string] = src;
  }
  return { ui: picked };
}

/** The root provider's set — public-page client islands only. */
export const ROOT_CLIENT_NAMESPACES = [
  "location",
  "notifications",
  "localeSwitcher",
  "agriHome.alert",
] as const;
