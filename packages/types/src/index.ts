/**
 * @agri/types — the single source of shared types across the five apps.
 *
 * Runtime-free by construction: this package must never ship executable code,
 * only `type` / `interface` declarations, so importing it from a Server
 * Component or an Edge route adds zero bytes.
 *
 * D01-B lands `backend/openapi.json`; `pnpm gen:types` then writes
 * `src/generated/openapi.ts` and the re-export below goes live.
 */

/** UUIDv7 — every id in the ecosystem (CLAUDE.md Constitution). */
export type Uuid = string & { readonly __brand: "uuid-v7" };

/** Opaque cursor for the mandated cursor-pagination on every list endpoint. */
export type Cursor = string & { readonly __brand: "cursor" };

/** All user-submitted content defaults to `pending` (CLAUDE.md Constitution). */
export type ModerationStatus = "pending" | "approved" | "rejected";

/** Shape every paginated list endpoint returns. */
export interface Page<T> {
  readonly items: readonly T[];
  readonly nextCursor: Cursor | null;
}

/** The three storefront themes; `data-theme` on each app's root element. */
export type SiteTheme = "theme-agri" | "theme-milk" | "theme-organic";

// D01-B → after `pnpm gen:types`, uncomment:
// export type { components, paths, operations } from "./generated/openapi.js";
