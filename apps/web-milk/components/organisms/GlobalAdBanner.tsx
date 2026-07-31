import { AdCarousel } from "@agri/ui";

import { HouseAdCard } from "@/components/molecules/HouseAdCard";

/**
 * Organism (M2): the global sliding head banner, mounted in the [locale]
 * layout so it renders on EVERY milk page. Sits BELOW the header - the
 * header's right cluster is off-limits (site-header.tsx documents the CLS
 * trap). Fixed heights reserve the box (NN3); the house fallback keeps it
 * filled when the engine is dark, so the layout never shifts either way.
 */
export function GlobalAdBanner() {
  return (
    <div className="mx-auto w-full max-w-[720px] px-4 pt-3">
      <AdCarousel
        slotKey="milk_global_header"
        heightClass="h-[72px] sm:h-[90px]"
        fallback={
          <HouseAdCard
            title="🥛 Post your need — vendors reply to you"
            vern="என் தேவை"
            href="/post-need"
          />
        }
      />
    </div>
  );
}
