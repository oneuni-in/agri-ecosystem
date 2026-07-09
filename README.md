# agri-ecosystem

Turborepo monorepo hosting the five Next.js 15 apps of the agri ecosystem and
the shared packages behind them.

## Quickstart

Requires Node (see [`.nvmrc`](.nvmrc)) and pnpm 11 — the version in
`packageManager` is enforced by corepack.

```bash
corepack enable
pnpm install
pnpm dev
```

`pnpm dev` boots all five apps concurrently:

| App | Package | Port | `data-theme` |
|---|---|---|---|
| Milk.in | `@agri/web-milk` | 3000 | `theme-milk` |
| OrganicStore.in | `@agri/web-organic` | 3001 | `theme-organic` |
| Agri.in | `@agri/web-agri` | 3002 | `theme-agri` |
| AgriID | `@agri/web-id` | 3003 | `theme-agri` |
| Agri Admin | `@agri/web-admin` | 3004 | `theme-agri` |

## Scripts

Every script fans out through turbo, so results are cached and a second run of
an unchanged task is a cache hit.

| Command | Does |
|---|---|
| `pnpm dev` | All five dev servers, persistent, uncached |
| `pnpm build` | `next build` per app |
| `pnpm lint` | ESLint 9 flat config, `--max-warnings 0` |
| `pnpm typecheck` | `tsc --noEmit`, strict, `any` banned |
| `pnpm gen:types` | Regenerates `@agri/types` from the backend OpenAPI schema |

## Layout

```
apps/
  web-milk/  web-organic/  web-agri/  web-id/  web-admin/
packages/
  config/       tsconfig bases · ESLint flat configs · Tailwind preset
  types/        shared types; OpenAPI-generated surface
  ui/           shared components (empty until D02)
  auth-client/  AgriID SSO client (stub until Sprint 1)
```

### Packages

All workspace packages are scoped `@agri/*` and private.

`@agri/config` is the single place build configuration lives. It exports
tsconfig bases (`base` / `next` / `library`), two ESLint flat configs
(`@agri/config/eslint` and `@agri/config/eslint/next`), and a Tailwind preset.
The preset is currently an **empty theme stub** — D02 fills it with the tokens
in [`docs/design-system.md`](docs/design-system.MD) §1. Per the Constitution,
hex values live in that preset and nowhere else.

Internal packages are consumed as TypeScript source rather than built
artifacts: they have no build step, and each app lists them in
`transpilePackages`. This keeps the dependency graph flat and turbo's build
task one level deep.

`pnpm gen:types` is wired but inert until D01-B lands `backend/openapi.json`;
it exits 0 with a note rather than failing a fresh clone.

## Conventions

Read [`CLAUDE.md`](CLAUDE.md) first — it is binding. In short: branch
`feat/dXX{a|b}-name` off `dev`, conventional commits, PR into `dev`, never
commit to `dev` or `main`.
