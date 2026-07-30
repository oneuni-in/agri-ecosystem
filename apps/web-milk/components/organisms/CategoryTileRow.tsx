import type { ProductCategory } from "@/lib/taxonomy";

import { CategoryTile } from "../molecules/CategoryTile";

/**
 * Organism: the home category row. A server component — no client JS, no
 * images, no hydration island, so it costs the LCP path nothing beyond its
 * own markup (NON-NEGOTIABLE 4).
 *
 * Renders nothing when the taxonomy is unavailable (backend down at build
 * time), so the page still builds and self-heals on the next revalidate.
 */
export function CategoryTileRow({
  categories,
  heading,
}: {
  categories: ProductCategory[];
  heading: string;
}) {
  if (categories.length === 0) return null;
  return (
    <nav aria-label={heading} data-testid="category-tile-row" className="w-full">
      <ul className="flex list-none gap-2 overflow-x-auto px-4 pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {categories.map((category) => (
          <li key={category.value}>
            <CategoryTile category={category} />
          </li>
        ))}
      </ul>
    </nav>
  );
}
