import { Badge, Card, Section } from "@agri/ui";
import { getTranslations } from "next-intl/server";

import { CATEGORY_MESSAGE_KEY, DAIRY_CATEGORIES } from "@/lib/categories";
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
                className="flex min-h-[38px] w-full items-center justify-center rounded-btn bg-brand text-[12px] font-bold text-white no-underline"
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
            <span className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className="flex h-11 w-11 flex-none items-center justify-center rounded-icon bg-brand-soft text-xl"
              >
                🥛
              </span>
              <span>
                <b className="block text-[13.5px] font-semibold text-ink">{brand.name}</b>
                <span className="block text-[11px] leading-relaxed text-sub">
                  {brand.products
                    .filter((p) => p.price_display)
                    .slice(0, 3)
                    .map((p) =>
                      `${typeLabels.get(p.milk_type ?? "") ?? ""} ${p.price_display}`.trim(),
                    )
                    .join(" · ")}
                </span>
              </span>
            </span>
            <span className="mt-2.5 block rounded-btn border border-cream-line bg-cream-deep py-2 text-center text-[12px] font-semibold text-ink">
              {t("nearest")}
            </span>
          </Link>
        ))}
      </div>
    </Section>
  );
}

/**
 * §8g — dairy service tiles. Schema-driven in the sense that matters: the
 * slugs are the D17/alembic business-category set (`lib/categories.ts`,
 * mirroring the migration), each linking its existing `/c/{category}` landing
 * page. Adding a category there lights up a tile with no change here.
 */
export async function DairyServices() {
  const [t, tCat] = await Promise.all([
    getTranslations("ui.home.services"),
    getTranslations("ui.dairyCategories"),
  ]);
  const icons: Record<string, string> = {
    veterinarian: "🐄",
    "feed-supplier": "🌾",
    "dairy-farm": "🏭",
    cooperative: "🤝",
  };
  return (
    <Section title={t("title")}>
      <div className="flex gap-2.5 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {DAIRY_CATEGORIES.map((slug) => (
          <Link
            key={slug}
            href={`/c/${slug}`}
            className="w-[118px] flex-none rounded-card border border-cream-line bg-card px-2 py-3.5 text-center no-underline"
            data-testid={`service-${slug}`}
          >
            <span
              aria-hidden="true"
              className="mx-auto mb-1.5 flex h-11 w-11 items-center justify-center rounded-icon bg-brand-soft text-[22px]"
            >
              {icons[slug]}
            </span>
            <b className="block text-[11.5px] font-semibold text-ink">
              {tCat(`${CATEGORY_MESSAGE_KEY[slug]}.name`)}
            </b>
          </Link>
        ))}
      </div>
    </Section>
  );
}
