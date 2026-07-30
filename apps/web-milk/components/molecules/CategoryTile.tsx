import { Link } from "@/i18n/navigation";
import type { ProductCategory } from "@/lib/taxonomy";

import { Icon } from "../atoms/Icon";
import { Label } from "../atoms/Label";

/** Molecule: one tappable category. Icon-first, then the schema's label.
 * `min-w`/`min-h` keep the tap target at the 44px floor the design system
 * requires (the D11 tap-target finding). */
export function CategoryTile({ category }: { category: ProductCategory }) {
  return (
    <Link
      href={`/p/${category.value}`}
      prefetch={false}
      data-testid={`category-tile-${category.value}`}
      className="flex min-h-[76px] min-w-[76px] shrink-0 flex-col items-center justify-center gap-1 rounded-card border border-line bg-card px-2 py-2 no-underline"
    >
      <Icon glyph={category.icon} />
      <Label en={category.label} vern={category.vern} />
    </Link>
  );
}
