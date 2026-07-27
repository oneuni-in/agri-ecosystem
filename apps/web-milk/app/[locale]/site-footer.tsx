import { LowDataToggle } from "@agri/ui";
import { getTranslations } from "next-intl/server";

/**
 * Minimal site footer whose only job today is hosting the D28 data-saver
 * toggle. It lives here, below the fold, and NOT in the header: the header's
 * right cluster already hydrates three islands (auth, coins, bell), and
 * adding a fourth item re-wrapped that row as they populated — measurably
 * pushing the hero h1 down (CLS 0.098 -> 0.136) and delaying LCP on the
 * Lighthouse-audited home page. The design doc specified a footer island
 * for exactly this reason.
 */
export async function SiteFooter() {
  const t = await getTranslations("ui.lowData");
  return (
    <footer className="mx-auto flex w-full max-w-[720px] justify-end px-4 py-6">
      <LowDataToggle label={t("label")} />
    </footer>
  );
}
