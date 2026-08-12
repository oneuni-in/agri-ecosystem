import { Badge, Card, IconTile, Section } from "@agri/ui";
import { getLocale, getTranslations } from "next-intl/server";

import { categoryIcon, categoryLabel, fetchBusinessCategories } from "@/lib/categories";
import { Link } from "@/i18n/navigation";
import type { ShowcaseProduct } from "@/lib/showcase";
import type { MilkCard } from "@/lib/milk";
import type { ProductCategory } from "@/lib/taxonomy";

/**
 * §7 — cross-vertical certified-products showcase. Everything renders from
 * `getShowcaseProducts()` (lib/showcase.ts), the single accessor over the
 * existing products/media engines. No new tables, no copied seed data in the
 * component: names, brand line, price and image all come from approved rows.
 */
export async function ShowcaseProducts({ products }: { products: ShowcaseProduct[] }) {
  if (products.length === 0) return null;
  const [t, tProduct] = await Promise.all([
    getTranslations("ui.home.products"),
    getTranslations("ui.product"),
  ]);
  return (
    <Section title={t("title")} see={t("seeAll")} seeHref="/search">
      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
        {products.map((product) => (
          <Card
            key={product.id}
            hover
            className="overflow-hidden border-cream-line p-0"
            data-testid={`showcase-${product.slug}`}
          >
            <div className="flex h-[84px] items-center justify-center bg-brand-soft">
              {product.image ? (
                // eslint-disable-next-line @next/next/no-img-element -- media-domain URL, same rule as AdImage
                <img
                  src={product.image}
                  alt={product.name}
                  loading="lazy"
                  decoding="async"
                  className="h-full w-full object-cover"
                />
              ) : (
                <span aria-hidden="true" className="text-[34px]">
                  🥛
                </span>
              )}
            </div>
            <div className="p-3">
              {product.categoryLabel ? (
                <Badge variant="cert">{product.categoryLabel}</Badge>
              ) : null}
              <b className="mt-1.5 block text-[12.5px] font-semibold text-ink">{product.name}</b>
              <div className="mb-2 text-[10.5px] text-muted">
                {product.businessName}
                {product.priceDisplay ? ` · ${product.priceDisplay}` : ""}
              </div>
              <Link
                href={`/directory/businesses/${product.businessSlug}`}
                className="flex min-h-[44px] w-full items-center justify-center rounded-btn bg-brand text-[12px] font-bold text-white no-underline"
              >
                {tProduct("whereToBuy")}
              </Link>
            </div>
          </Card>
        ))}
      </div>
    </Section>
  );
}

/**
 * §8f — brands available in this pincode. Cards come from the SAME
 * `covers()`-backed blend as the vendor grid (`home.brands`, the `shop` type),
 * so a brand with no presence here simply is not in the list and the whole
 * section hides. Price lines are the brand's own approved listings.
 */
export async function BrandsAvailable({
  brands,
  milkTypes,
  pincode,
}: {
  brands: MilkCard[];
  milkTypes: ProductCategory[];
  pincode: string;
}) {
  if (brands.length === 0) return null; // §25: hidden when the pincode has no brand presence
  const t = await getTranslations("ui.home.brands");
  const typeLabels = new Map(milkTypes.map((m) => [m.value, m.label]));
  return (
    <Section title={t("title", { pincode })} see={t("all")} seeHref="/search">
      <div className="grid gap-2.5 md:grid-cols-2 lg:grid-cols-3">
        {brands.map((brand) => (
          <Link
            key={brand.id}
            href={`/directory/businesses/${brand.slug}?pin=${pincode}`}
            className="rounded-card border border-cream-line bg-card p-3.5 no-underline"
            data-testid={`home-brand-${brand.slug}`}
          >
            <IconTile
              variant="row"
              icon="🥛"
              title={brand.name}
              sub={brand.products
                .filter((p) => p.price_display)
                .slice(0, 3)
                .map((p) => `${typeLabels.get(p.milk_type ?? "") ?? ""} ${p.price_display}`.trim())
                .join(" · ")}
              footer={t("nearest")}
            />
          </Link>
        ))}
      </div>
    </Section>
  );
}

/**
 * §8g — dairy service tiles, fully data-driven (U1b): the tile SET is the
 * public taxonomy read (categories with ≥1 active business), each linking
 * its `/c/{category}` landing page. Adding a category row + one active
 * business lights up a tile with no change here; icons fall back to 🥛 for
 * a slug this map has never seen. Collapses when the taxonomy is dark.
 */
export async function DairyServices() {
  const [t, locale, categories] = await Promise.all([
    getTranslations("ui.home.services"),
    getLocale(),
    fetchBusinessCategories(),
  ]);
  if (categories.length === 0) return null;
  return (
    <Section title={t("title")}>
      <div className="flex gap-2.5 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {categories.map((category) => (
          <Link
            key={category.slug}
            href={`/c/${category.slug}`}
            className="w-[118px] flex-none rounded-card border border-cream-line bg-card px-2 py-3.5 text-center no-underline"
            data-testid={`service-${category.slug}`}
          >
            <IconTile icon={categoryIcon(category.slug)} title={categoryLabel(category, locale)} />
          </Link>
        ))}
      </div>
    </Section>
  );
}
