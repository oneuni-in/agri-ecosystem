"use client";

/**
 * A-U1 W2 — the /categories search island (A2 `.cat-search` + live filter).
 * Client-side FILTER only, no fetch: the server serializes the registry
 * rows (slug + EN/TA/HI names in `haystack`) and this island narrows the
 * grid as the visitor types. Initial value comes from `?q=` — the home
 * search band's GET target. All strings arrive as props (server-translated)
 * so this island needs no client message namespace.
 */
import { CategoryGroup, CategoryTile } from "@agri/ui";
import { useState } from "react";

export interface FilterTile {
  slug: string;
  icon: string;
  label: string;
  vernacular: string;
  soon: boolean;
  /** Lowercased slug + EN/TA/HI names — what the query matches against. */
  haystack: string;
}

export interface FilterGroup {
  key: string;
  label: string;
  /** "· 7 live" / "· 11 · Stage B" — server-built from registry counts. */
  count: string;
  dot: string;
  tint: "green" | "sand" | "aqua" | "lilac" | "peach";
  items: FilterTile[];
}

export function CategoriesFilter({
  groups,
  initialQuery,
  inputLabel,
  placeholder,
  noMatches,
  soonLabel,
}: {
  groups: FilterGroup[];
  initialQuery: string;
  inputLabel: string;
  placeholder: string;
  noMatches: string;
  soonLabel: string;
}) {
  const [query, setQuery] = useState(initialQuery);
  const needle = query.trim().toLowerCase();
  const filtered = groups
    .map((group) => ({
      ...group,
      items: needle
        ? group.items.filter((tile) => tile.haystack.includes(needle))
        : group.items,
    }))
    .filter((group) => group.items.length > 0);

  return (
    <div data-testid="categories-filter">
      <div className="mt-3.5 flex max-w-[560px] items-center gap-2.5 rounded-[14px] border border-cream-line bg-card py-1.5 pl-4 pr-1.5">
        <label htmlFor="catq" className="sr-only">
          {inputLabel}
        </label>
        <input
          id="catq"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          className="min-h-[44px] min-w-0 flex-1 border-0 bg-transparent text-sm text-ink focus:outline-none"
        />
        <span aria-hidden="true" className="pr-2 text-[13px] text-muted">
          🔍
        </span>
      </div>

      {filtered.length === 0 ? (
        <p className="mt-5 text-[12.5px] text-muted">{noMatches}</p>
      ) : (
        filtered.map((group) => (
          <CategoryGroup
            key={group.key}
            label={
              <>
                <span
                  aria-hidden="true"
                  className={`h-2.5 w-2.5 flex-shrink-0 rounded-[3px] ${group.dot}`}
                />
                {group.label}
                <span className="text-[10.5px] font-normal normal-case text-muted">
                  {group.count}
                </span>
              </>
            }
          >
            {group.items.map((tile) => (
              <CategoryTile
                key={tile.slug}
                href={`/c/${tile.slug}`}
                icon={tile.icon}
                label={tile.label}
                vernacular={tile.vernacular}
                tint={group.tint}
                soon={tile.soon}
                soonLabel={soonLabel}
              />
            ))}
          </CategoryGroup>
        ))
      )}
    </div>
  );
}
