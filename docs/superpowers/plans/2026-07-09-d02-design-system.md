# D02 Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill `packages/config` (tokens) and `packages/ui` (18 components + 10 composites + i18n catalogs + SEO primitives) so a demo route in web-agri is visually indistinguishable from `docs/design-reference/preview_frontend.html`, per `docs/design-system.md`.

**Architecture:** All hex lives in the Tailwind preset (`packages/config/tailwind/preset.js`) as CSS custom properties injected via a plugin (`addBase`) keyed on `[data-theme]`, plus `theme.extend` mappings so components use only token classes (`bg-brand`, `rounded-card`, `shadow-lift`…). `@agri/ui` ships TS source (no build step; apps compile via `transpilePackages`), stays server-component-first (`"use client"` only in Modal/Toast/demo switch), and exposes subpath exports for `fonts`, `seo`, `i18n`. Fonts load once via `next/font/google` in a shared module. The demo route switches theme via `?theme=` searchParam (server-rendered → screenshot-friendly, keyboard-operable).

**Tech Stack:** Next 15.5.20 · React 19.2.7 · Tailwind 3.4.19 (presets API — do NOT upgrade to v4) · next-intl (no-routing mode) · Radix (`react-dialog`, `react-toast`) · cva/clsx/tailwind-merge · schema-dts · Playwright (screenshots) · Lighthouse (a11y check).

## Global Constraints

- Toolchain: Node 24.16.0 / pnpm 11.10.0 / Tailwind **3.4** — installed toolchain wins over any spec text saying Node 20/pnpm 9 (memory: toolchain-overrides-spec).
- Git: branch `feat/d02-design-system` (already checked out), conventional commits, PR targets `dev`, never main. Final commit message theme: `feat(d02): design system per spec v1`.
- **No raw hex outside `packages/config`** — enforced by `scripts/check-hex.mjs` (Task 2). This includes the demo route. rgba() literals in ui code are also banned (put them in the preset).
- Internal packages ship TS source; `exports` point at `src/*`; no dist builds (memory: d01a-layout-decisions).
- Every interactive element ≥44px effective target (use `.tap-target` utility where visuals are smaller), focus ring 3px `--accent` offset 2 (never removed), `prefers-reduced-motion` respected (`motion-reduce:` variants on every transition/animation).
- SEO module: zero `"use client"`. Components: server-safe except Modal/Toast.
- Mockup wins over library defaults. Sponsored badge is ALWAYS "★ Sponsored". Emoji icons are v1-official (design-system.md §4).
- Ports: agri app = 3002. Demo route = `http://localhost:3002/demo`.
- Verification per task = `pnpm typecheck && pnpm lint` (turbo) + `node scripts/check-hex.mjs`; visual verification happens in Task 12–13 (build, screenshots vs mockup, Lighthouse). No JS unit-test infra exists in this repo; type-level tests (`@ts-expect-error`) cover the "invalid JSON-LD fails typecheck" requirement.

---

### Task 1: Design tokens — fill the Tailwind preset

**Files:**
- Modify: `packages/config/tailwind/preset.js` (replace stub)
- Modify: `packages/config/tailwind/preset.d.ts` (keep in sync if it types more than `Config`)

**Interfaces:**
- Produces (Tailwind classes all later tasks consume): colors `brand, brand-deep, brand-soft, accent, ink, sub, paper, page, card, line, call, wa, wa-soft, wa-deep, wa-line, coins-bg, coins-fg, alert-bg, alert-line, helpband, verified-bg, verified-fg, sponsored-bg, sponsored-fg, cert-bg, cert-fg, rating, ghost, glass, certgold-bg, certgold-line, tint-{green,sand,blush,peach,bluegray,aqua,cream,lilac,gold,violet,stone,mist,sky,blue,leaf,sage,fern}`; radii `rounded-{card:16,btn:12,pill:99,band:18,icon:14}`; shadows `shadow-{lift,search,pin,callglow,nav,ai}`; bg images `bg-{header-gradient,cta-gradient,eco-milk,eco-organic,eco-coins,gold-gradient}`; fonts `font-display`, `font-body`; utility classes `.vern`, `.tap-target`; base styles (body, :focus-visible, `[data-theme]` vars).

- [ ] **Step 1: Write the preset**

```js
/**
 * @agri/config — Tailwind preset. THE only place hex colors are allowed
 * (CLAUDE.md: tokens only — no raw hex in app code).
 * Values are exact from docs/design-system.md §1; the mockup at
 * docs/design-reference/preview_frontend.html is the visual source of truth.
 * @type {import("tailwindcss").Config}
 */
import plugin from "tailwindcss/plugin";

/** §1.1 per-site themes, switched via data-theme on the app root. */
const themes = {
  "theme-agri":    { "--brand": "#2C6E35", "--brand-deep": "#1E4E26", "--brand-soft": "#E8F2E6", "--accent": "#E9A61C" },
  "theme-milk":    { "--brand": "#2563A8", "--brand-deep": "#174A85", "--brand-soft": "#E9F1FA", "--accent": "#E9A61C" },
  "theme-organic": { "--brand": "#4A6B2A", "--brand-deep": "#35511C", "--brand-soft": "#EFF3E4", "--accent": "#B5541C" },
};

/** §1.2 shared neutrals & semantics (+ recipe colors lifted from the mockup). */
const shared = {
  "--ink": "#1D2A20", "--sub": "#5A6A5D", "--paper": "#F7F8F3", "--page-bg": "#E9EBE2",
  "--card": "#FFFFFF", "--line": "#E2E7DA",
  "--call": "#1E9E4A", "--wa": "#22B45A",
  "--wa-soft": "#E6F8EC", "--wa-deep": "#157A3C", "--wa-line": "#BDE8CC",
  "--coins-bg": "#FFF3D6", "--coins-fg": "#8A5B00",
  "--alert-bg": "#FFF6E4", "--alert-line": "#F0DCA8",
  "--helpband": "#153A1D",
  "--verified-bg": "#E1F3E5", "--verified-fg": "#156A2E",
  "--sponsored-bg": "#FFF1D2", "--sponsored-fg": "#8A5B00",
  "--cert-bg": "#EAF2DC", "--cert-fg": "#3E5A14",
  "--rating": "#C77700",
  "--ghost": "#F2F4EC",
  "--glass": "rgba(255,255,255,.16)",
};

/** Pastel icon-square tints used by CategoryTile / ListingCard / ProductCard. */
const tint = {
  green: "#E8F2E6", sand: "#F4EEDB", blush: "#FBEAE2", peach: "#FDEFD8",
  bluegray: "#EAF0F7", aqua: "#E4F3F1", cream: "#FDF3D9", lilac: "#EDEBF8",
  gold: "#FFF1D2", violet: "#F0EAF6", stone: "#EFEADF", mist: "#F2F4EC",
  sky: "#E4F0F7", blue: "#E9F1FA", leaf: "#EAF2DC", sage: "#EFF3E4", fern: "#EFF6EA",
};

export const agriPreset = {
  content: [],
  theme: {
    extend: {
      colors: {
        brand: "var(--brand)", "brand-deep": "var(--brand-deep)", "brand-soft": "var(--brand-soft)",
        accent: "var(--accent)",
        ink: "var(--ink)", sub: "var(--sub)", paper: "var(--paper)", page: "var(--page-bg)",
        card: "var(--card)", line: "var(--line)",
        call: "var(--call)", wa: "var(--wa)",
        "wa-soft": "var(--wa-soft)", "wa-deep": "var(--wa-deep)", "wa-line": "var(--wa-line)",
        "coins-bg": "var(--coins-bg)", "coins-fg": "var(--coins-fg)",
        "alert-bg": "var(--alert-bg)", "alert-line": "var(--alert-line)",
        helpband: "var(--helpband)",
        "verified-bg": "var(--verified-bg)", "verified-fg": "var(--verified-fg)",
        "sponsored-bg": "var(--sponsored-bg)", "sponsored-fg": "var(--sponsored-fg)",
        "cert-bg": "var(--cert-bg)", "cert-fg": "var(--cert-fg)",
        rating: "var(--rating)", ghost: "var(--ghost)", glass: "var(--glass)",
        "certgold-bg": "#FFFBEE", "certgold-line": "#CBB77A",
        tint,
      },
      borderRadius: { card: "16px", btn: "12px", pill: "99px", band: "18px", icon: "14px" },
      fontFamily: {
        display: ["var(--font-display)", "var(--font-body)", "system-ui", "sans-serif"],
        body: ["var(--font-body)", "var(--font-tamil)", "var(--font-devanagari)", "system-ui", "sans-serif"],
      },
      boxShadow: {
        lift: "0 6px 16px rgba(0,0,0,.08)",
        search: "0 4px 18px rgba(0,0,0,.12)",
        pin: "0 6px 20px rgba(0,0,0,.18)",
        callglow: "0 4px 14px rgba(30,158,74,.4)",
        nav: "0 -6px 20px rgba(0,0,0,.06)",
        ai: "0 4px 12px color-mix(in srgb, var(--brand) 40%, transparent)",
      },
      backgroundImage: {
        "header-gradient": "linear-gradient(160deg, var(--brand-deep), var(--brand))",
        "cta-gradient": "linear-gradient(140deg, var(--brand-deep), var(--brand))",
        "eco-milk": "linear-gradient(140deg, #174A85, #2563A8)",
        "eco-organic": "linear-gradient(140deg, #35511C, #4A6B2A)",
        "eco-coins": "linear-gradient(140deg, #8A5B00, #C98A10)",
        "gold-gradient": "linear-gradient(140deg, #8A5B00, #B5541C)",
      },
    },
  },
  plugins: [
    plugin(({ addBase, addComponents, addUtilities }) => {
      addBase({
        ":root": { ...shared, ...themes["theme-agri"] },
        '[data-theme="theme-agri"]': themes["theme-agri"],
        '[data-theme="theme-milk"]': themes["theme-milk"],
        '[data-theme="theme-organic"]': themes["theme-organic"],
        body: {
          backgroundColor: "var(--page-bg)",
          color: "var(--ink)",
          fontFamily: "var(--font-body), var(--font-tamil), var(--font-devanagari), system-ui, sans-serif",
          fontSize: "15px",
          lineHeight: "1.5",
          "-webkit-font-smoothing": "antialiased",
        },
        ":focus-visible": {
          outline: "3px solid var(--accent)",
          outlineOffset: "2px",
          borderRadius: "6px",
        },
      });
      addComponents({
        // §1.3 — under EVERY category label and key CTA, own line.
        ".vern": {
          display: "block", fontSize: ".78em", fontWeight: "500",
          opacity: ".85", lineHeight: "1.3",
        },
      });
      addUtilities({
        // Expands the hit area of visually-small pills to the 44px minimum
        // (§1.5) without changing their rendered size.
        ".tap-target": { position: "relative" },
        ".tap-target::after": {
          content: '""', position: "absolute", left: "50%", top: "50%",
          transform: "translate(-50%, -50%)",
          width: "max(100%, 44px)", height: "max(100%, 44px)",
        },
      });
    }),
  ],
};

export default agriPreset;
```

- [ ] **Step 2: Verify** — `pnpm typecheck && pnpm lint` at repo root: PASS. Then quick smoke: `pnpm --filter @agri/web-agri build` must succeed (preset is consumed by every app's tailwind.config).
- [ ] **Step 3: Commit** — `git commit -m "feat(d02): design tokens - themes, neutrals, radii, shadows, gradients in tailwind preset"`

---

### Task 2: Hex-ban check script

**Files:**
- Create: `scripts/check-hex.mjs`
- Modify: `package.json` (root — add `"check:hex": "node scripts/check-hex.mjs"`)

**Interfaces:**
- Produces: `pnpm check:hex` — exits 1 listing `path:line` for any `#RGB/#RGBA/#RRGGBB/#RRGGBBAA` or `rgba(`/`rgb(` literal in `apps/**` and `packages/ui/**` source (`.ts .tsx .css`), excluding `node_modules`, `.next`, `.turbo`. `packages/config` is exempt (tokens live there).

- [ ] **Step 1: Write the script**

```js
// Bans raw color literals outside packages/config (CLAUDE.md: tokens only).
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

const ROOTS = ["apps", "packages/ui"];
const EXTS = new Set([".ts", ".tsx", ".css"]);
const SKIP = new Set(["node_modules", ".next", ".turbo", "dist"]);
const HEX = /#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b|rgba?\(/;

const violations = [];
function walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (SKIP.has(entry.name)) continue;
    const path = join(dir, entry.name);
    if (entry.isDirectory()) { walk(path); continue; }
    if (![...EXTS].some((ext) => entry.name.endsWith(ext))) continue;
    readFileSync(path, "utf8").split("\n").forEach((line, i) => {
      if (HEX.test(line)) violations.push(`${relative(".", path)}:${i + 1}  ${line.trim()}`);
    });
  }
}
ROOTS.forEach(walk);

if (violations.length > 0) {
  console.error(`check:hex FAILED — ${violations.length} raw color literal(s); use preset tokens:\n`);
  violations.forEach((v) => console.error("  " + v));
  process.exit(1);
}
console.log("check:hex OK — no raw color literals in apps/ or packages/ui/");
```

- [ ] **Step 2: Verify it fails on a violation** — temporarily add `const x = "#FFF";` to `packages/ui/src/index.ts`, run `pnpm check:hex`, expect exit 1 naming the line; revert; run again, expect `check:hex OK`.
- [ ] **Step 3: Commit** — `git commit -m "ci(d02): hex-ban check script - tokens only outside packages/config"`

---

### Task 3: Fonts + app shells

**Files:**
- Create: `packages/ui/src/fonts.ts`
- Modify: `packages/ui/package.json` (add `"./fonts": "./src/fonts.ts"` export; add `next` to peer+dev deps)
- Modify: all 5 `apps/web-*/app/layout.tsx` (add `className={fontVariables}` to `<html>`)

**Interfaces:**
- Produces: `import { fontVariables } from "@agri/ui/fonts"` — a className string defining `--font-display/--font-body/--font-tamil/--font-devanagari` consumed by the preset's `fontFamily`/body base styles.

- [ ] **Step 1: Write fonts.ts** (next/font works inside transpiled packages)

```ts
import {
  Bricolage_Grotesque, Noto_Sans_Devanagari, Noto_Sans_Tamil, Public_Sans,
} from "next/font/google";

/** Display 600/800 (design-system.md §1.3). */
const display = Bricolage_Grotesque({ subsets: ["latin"], weight: ["600", "800"], variable: "--font-display", display: "swap" });
const body = Public_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700", "800"], variable: "--font-body", display: "swap" });
const tamil = Noto_Sans_Tamil({ subsets: ["tamil"], weight: ["500", "700"], variable: "--font-tamil", display: "swap" });
const devanagari = Noto_Sans_Devanagari({ subsets: ["devanagari"], weight: ["500", "700"], variable: "--font-devanagari", display: "swap" });

/** Put on the <html> element of every app. */
export const fontVariables = [display.variable, body.variable, tamil.variable, devanagari.variable].join(" ");
```

- [ ] **Step 2: Wire each layout** — `<html lang="en" data-theme={THEME} className={fontVariables}>` in all 5 apps (import from `@agri/ui/fonts`). Body needs no classes — base styles come from the preset.
- [ ] **Step 3: Verify** — `pnpm --filter @agri/web-agri build` PASS (fonts download at build). `pnpm typecheck && pnpm lint` PASS.
- [ ] **Step 4: Commit** — `git commit -m "feat(d02): display/body/vernacular fonts wired into all five app shells"`

---

### Task 4: @agri/ui infra — cn(), deps, shadcn architecture, exports map

**Files:**
- Modify: `packages/ui/package.json` (deps: `clsx`, `tailwind-merge`, `class-variance-authority`, `@radix-ui/react-dialog`, `@radix-ui/react-toast`, `schema-dts`; peerDeps `react`, `react-dom`, `next`; exports: `"."`, `"./fonts"`, `"./seo"`, `"./i18n"`)
- Create: `packages/ui/components.json` (shadcn config — marks the shadcn architecture; CLI's default HSL theme injection is deliberately NOT run because mockup tokens override library defaults per design-system.md rule)
- Create: `packages/ui/src/lib/cn.ts`

**Interfaces:**
- Produces: `cn(...inputs: ClassValue[]): string` (clsx + tailwind-merge), used by every component.

- [ ] **Step 1: cn.ts**

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 2: components.json**

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": true,
  "tsx": true,
  "tailwind": { "config": "../../apps/web-agri/tailwind.config.ts", "css": "../../apps/web-agri/app/globals.css", "baseColor": "neutral", "cssVariables": true },
  "aliases": { "components": "src/components", "utils": "src/lib/cn" }
}
```

- [ ] **Step 3: Install** — `pnpm add --filter @agri/ui clsx tailwind-merge class-variance-authority @radix-ui/react-dialog @radix-ui/react-toast schema-dts` then dedupe/verify lockfile.
- [ ] **Step 4: Verify + commit** — `pnpm typecheck` PASS. `git commit -m "feat(d02): ui package infra - cn util, radix/cva deps, shadcn architecture"`

---

### Task 5: Core primitives — Button, CallButton, WhatsAppButton, Card, Badge, RatingStars, Skeleton, EmptyState

**Files:**
- Create: `packages/ui/src/components/button.tsx`, `card.tsx`, `badge.tsx`, `rating-stars.tsx`, `skeleton.tsx`, `empty-state.tsx`
- Modify: `packages/ui/src/index.ts` (export all)

**Interfaces (produced, consumed by Tasks 7/9/12):**
- `Button({ variant: "call"|"wa"|"ghost"|"brand", ... })` + `buttonVariants(opts)` for anchor styling. Base ≥44px tall, `rounded-btn`, `font-extrabold text-sm`, `flex-1`.
- `CallButton({ label, href? })` → `📞 {label}`; `WhatsAppButton({ label, href? })` → WA recipe.
- `Card({ hover?: boolean })` — white, `border-line`, `rounded-card`, no shadow at rest; hover = lift.
- `Badge({ variant: "verified"|"sponsored"|"cert", children? })` — sponsored ALWAYS renders `★ Sponsored` (children ignored by type: sponsored variant takes no children).
- `RatingStars({ value })` → `★ {value}` `text-rating font-extrabold text-[13px]`.
- `Skeleton({ width, height, rounded? })` — required fixed dims (CLS 0), `animate-pulse motion-reduce:animate-none`.
- `EmptyState({ icon, title, description?, action? })`.

- [ ] **Step 1: button.tsx** (cva; exact mockup recipes `.abtn.*`)

```tsx
import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "../lib/cn";

export const buttonVariants = cva(
  "inline-flex min-h-[44px] flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-btn px-2 py-3 text-sm font-extrabold transition-[transform,box-shadow] duration-150 motion-reduce:transition-none",
  {
    variants: {
      variant: {
        call: "bg-call text-white",
        wa: "border-[1.5px] border-wa-line bg-wa-soft text-wa-deep",
        ghost: "bg-ghost text-ink",
        brand: "bg-brand text-white",
      },
    },
    defaultVariants: { variant: "ghost" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, type = "button", ...props }: ButtonProps) {
  return <button type={type} className={cn(buttonVariants({ variant }), className)} {...props} />;
}

/** Call leads every vendor card (UX law 4). Renders `tel:` link when href given. */
export function CallButton({ label, href, className }: { label: string; href?: string; className?: string }) {
  const classes = cn(buttonVariants({ variant: "call" }), "no-underline", className);
  return href
    ? <a href={href} className={classes}>📞 {label}</a>
    : <Button variant="call" className={className}>📞 {label}</Button>;
}

export function WhatsAppButton({ label, href, className }: { label: string; href?: string; className?: string }) {
  const classes = cn(buttonVariants({ variant: "wa" }), "no-underline", className);
  return href
    ? <a href={href} className={classes}>{label}</a>
    : <Button variant="wa" className={className}>{label}</Button>;
}
```

- [ ] **Step 2: card.tsx**

```tsx
import type { HTMLAttributes } from "react";
import { cn } from "../lib/cn";

export interface CardProps extends HTMLAttributes<HTMLDivElement> { hover?: boolean }

export function Card({ className, hover = false, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-card border border-line bg-card",
        hover &&
          "transition-[transform,box-shadow] duration-150 hover:-translate-y-0.5 hover:shadow-lift motion-reduce:transition-none motion-reduce:hover:translate-y-0",
        className,
      )}
      {...props}
    />
  );
}
```

- [ ] **Step 3: badge.tsx** (sponsored label is non-negotiable)

```tsx
import type { ReactNode } from "react";
import { cn } from "../lib/cn";

const base = "inline-flex items-center gap-1 rounded-pill px-[9px] py-[3px] text-[11px] font-extrabold";

type BadgeProps =
  | { variant: "sponsored"; children?: never; className?: string }
  | { variant: "verified" | "cert"; children: ReactNode; className?: string };

export function Badge(props: BadgeProps) {
  if (props.variant === "sponsored") {
    return <span className={cn(base, "bg-sponsored-bg text-sponsored-fg", props.className)}>★ Sponsored</span>;
  }
  const palette = props.variant === "verified" ? "bg-verified-bg text-verified-fg" : "bg-cert-bg text-cert-fg";
  return <span className={cn(base, palette, props.className)}>{props.children}</span>;
}
```

- [ ] **Step 4: rating-stars.tsx**

```tsx
import { cn } from "../lib/cn";

/** `★ 4.7` — number-first, never icon rows (design-system.md §2). */
export function RatingStars({ value, className }: { value: number | string; className?: string }) {
  return <span className={cn("text-[13px] font-extrabold text-rating", className)}>★ {value}</span>;
}
```

- [ ] **Step 5: skeleton.tsx** (fixed dims required → CLS 0)

```tsx
import { cn } from "../lib/cn";

export function Skeleton({ width, height, className }: { width: string; height: string; className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded-card bg-line motion-reduce:animate-none", className)}
      style={{ width, height }}
    />
  );
}
```

- [ ] **Step 6: empty-state.tsx**

```tsx
import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export function EmptyState({ icon, title, description, action, className }: {
  icon: ReactNode; title: ReactNode; description?: ReactNode; action?: ReactNode; className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center gap-2 rounded-card border border-line bg-card p-8 text-center", className)}>
      <span className="text-[44px] leading-none" aria-hidden="true">{icon}</span>
      <p className="text-[15.5px] font-extrabold">{title}</p>
      {description ? <p className="text-[12.5px] text-sub">{description}</p> : null}
      {action ? <div className="mt-2 flex w-full max-w-[280px]">{action}</div> : null}
    </div>
  );
}
```

- [ ] **Step 7: Export from index.ts, verify (`pnpm typecheck && pnpm lint && pnpm check:hex`), commit** — `feat(d02): core primitives - button, card, badge, rating, skeleton, empty-state`

---

### Task 6: Header pills + search + pincode — CoinsPill, LocationPill, LangSwitcher, GpsPill, SearchBar, PincodeInput

**Files:**
- Create: `packages/ui/src/components/pills.tsx` (CoinsPill, LocationPill, LangSwitcher, GpsPill, Avatar)
- Create: `packages/ui/src/components/search-bar.tsx`, `pincode-input.tsx`
- Modify: `packages/ui/src/index.ts`

**Interfaces:**
- `CoinsPill({ amount })` — gold pill `🪙 {amount}`.
- `LocationPill({ children })`, `LangSwitcher({ label? })` (default `🌐 EN · த · हி`), `GpsPill({ children })` — glass pills, `.tap-target`.
- `Avatar({ initial, ariaLabel })` — 38px white circle.
- `SearchBar({ placeholder, ariaLabel, hint?, showCam?, micLabel, camLabel? })` — floating white bar; mic right-most 46px accent square; hint line rendered below in white/85.
- `PincodeInput({ defaultValue?, inputLabel, findLabel })` — 6-digit numeric `.15em` tracking + brand Find.

- [ ] **Step 1: pills.tsx**

```tsx
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "../lib/cn";

type PillButtonProps = ButtonHTMLAttributes<HTMLButtonElement>;

const glass = "tap-target flex items-center gap-1.5 rounded-pill border border-white/30 bg-glass px-3.5 py-[7px] text-[13px] font-semibold text-white";

export function LocationPill({ className, children, ...props }: PillButtonProps) {
  return <button type="button" className={cn(glass, className)} {...props}>{children}</button>;
}

export function LangSwitcher({ label = "🌐 EN · த · हि", className, ...props }: PillButtonProps & { label?: ReactNode }) {
  return <button type="button" className={cn(glass, className)} {...props}>{label}</button>;
}

export function GpsPill({ className, children, ...props }: PillButtonProps) {
  return (
    <button type="button"
      className={cn("tap-target mt-2.5 inline-flex items-center gap-[7px] rounded-pill border border-white/35 bg-glass px-[18px] py-[9px] text-[13.5px] font-bold text-white", className)}
      {...props}>
      {children}
    </button>
  );
}

export function CoinsPill({ amount, className, ...props }: PillButtonProps & { amount: string | number }) {
  return (
    <button type="button" className={cn("tap-target flex items-center gap-[5px] rounded-pill bg-coins-bg px-[13px] py-[7px] text-[13px] font-extrabold text-coins-fg", className)} {...props}>
      🪙 {amount}
    </button>
  );
}

export function Avatar({ initial, className, "aria-label": ariaLabel, ...props }: PillButtonProps & { initial: string }) {
  return (
    <button type="button" aria-label={ariaLabel}
      className={cn("tap-target flex h-[38px] w-[38px] items-center justify-center rounded-full bg-white text-[15px] font-extrabold text-ink", className)}
      {...props}>
      {initial}
    </button>
  );
}
```

- [ ] **Step 2: search-bar.tsx** — outer `div`: `flex items-center gap-2.5 rounded-card bg-card py-1.5 pl-[18px] pr-1.5 shadow-search`; leading `<span aria-hidden className="text-lg">🔍</span>`; `<input className="min-w-0 flex-1 border-none bg-transparent py-3 text-base text-ink placeholder:text-sub focus:outline-none" />`; optional cam `<button className="flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-btn bg-ghost text-xl">📷</button>`; mic LAST: same but `bg-accent text-white`; hint below: `<div className="mt-2 px-1 text-[12.5px] font-medium text-white/85">`.
- [ ] **Step 3: pincode-input.tsx** — form `mx-auto flex w-full max-w-[520px] gap-1.5 rounded-card bg-card p-1.5 shadow-pin`; input `min-w-0 flex-1 border-none bg-transparent px-3.5 py-3 text-lg font-bold tracking-[.15em] text-ink focus:outline-none` with `inputMode="numeric" maxLength={6} pattern="[0-9]*"`; find button `min-h-[44px] rounded-btn bg-brand px-[22px] text-[15px] font-extrabold text-white`.
- [ ] **Step 4: Export, verify, commit** — `feat(d02): header pills, search bar, pincode input`

---

### Task 7: CategoryTile, BottomNav, ListingCard

**Files:**
- Create: `packages/ui/src/components/category-tile.tsx`, `bottom-nav.tsx`, `listing-card.tsx`
- Modify: `packages/ui/src/index.ts`

**Interfaces:**
- `type Tint = "green"|"sand"|...|"fern"` exported from `category-tile.tsx`; `tintClass: Record<Tint, string>` maps to literal `bg-tint-*` classes (Tailwind can't see computed names).
- `CategoryTile({ icon, label, vernacular, tint, href })` — anchor, min-h 104px, 52px icon square, 12px/700 EN + `.vern` line, hover lift + brand border.
- `BottomNav({ items: BottomNavItem[] })`, `BottomNavItem = { icon; label; href?; active?; ai?: boolean }` — 5 slots; ai item = 46px brand circle raised −22px, 4px white ring.
- `ListingCard({ badge?, icon, tint, title, meta, priceTag?, extraMeta?, actions? })` — anatomy: badge row → 56px icon square + 15.5/800 title + 12.5 meta → price-tag → action row.

- [ ] **Step 1: category-tile.tsx**

```tsx
import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export type Tint =
  | "green" | "sand" | "blush" | "peach" | "bluegray" | "aqua" | "cream" | "lilac"
  | "gold" | "violet" | "stone" | "mist" | "sky" | "blue" | "leaf" | "sage" | "fern";

/** Literal class names so Tailwind's scanner sees them. */
export const tintClass: Record<Tint, string> = {
  green: "bg-tint-green", sand: "bg-tint-sand", blush: "bg-tint-blush", peach: "bg-tint-peach",
  bluegray: "bg-tint-bluegray", aqua: "bg-tint-aqua", cream: "bg-tint-cream", lilac: "bg-tint-lilac",
  gold: "bg-tint-gold", violet: "bg-tint-violet", stone: "bg-tint-stone", mist: "bg-tint-mist",
  sky: "bg-tint-sky", blue: "bg-tint-blue", leaf: "bg-tint-leaf", sage: "bg-tint-sage", fern: "bg-tint-fern",
};

/** Icon + English + mother tongue on every tile (UX law 1). */
export function CategoryTile({ icon, label, vernacular, tint, href, className }: {
  icon: ReactNode; label: ReactNode; vernacular: ReactNode; tint: Tint; href: string; className?: string;
}) {
  return (
    <a href={href}
      className={cn(
        "flex min-h-[104px] flex-col items-center justify-start gap-1.5 rounded-card border-[1.5px] border-line bg-card px-1.5 pb-2.5 pt-3 text-center text-ink no-underline",
        "transition-[transform,box-shadow,border-color] duration-100 hover:-translate-y-0.5 hover:border-brand hover:shadow-lift",
        "motion-reduce:transition-none motion-reduce:hover:translate-y-0",
        "max-sm:min-h-[98px] max-sm:px-1 max-sm:pb-2 max-sm:pt-2.5",
        className,
      )}>
      <span aria-hidden="true"
        className={cn("flex h-[52px] w-[52px] items-center justify-center rounded-icon text-[30px] leading-none max-sm:h-[46px] max-sm:w-[46px] max-sm:text-[26px]", tintClass[tint])}>
        {icon}
      </span>
      <b className="text-xs font-bold leading-[1.25]">
        {label}
        <span className="vern text-[10.5px]">{vernacular}</span>
      </b>
    </a>
  );
}
```

- [ ] **Step 2: bottom-nav.tsx** — `nav`: `sticky bottom-0 z-[60] flex justify-around border-t border-line bg-card px-1 pb-2.5 pt-2 shadow-nav`; item (a or button): `flex min-w-[60px] min-h-[44px] flex-col items-center gap-0.5 text-[10.5px] font-bold text-sub no-underline` + active `text-brand-deep`; icon span `text-[21px] leading-none`; ai icon span: `mt-[-22px] flex h-[46px] w-[46px] items-center justify-center rounded-full border-4 border-card bg-brand text-white shadow-ai`.
- [ ] **Step 3: listing-card.tsx** — Card wrapper `flex flex-col gap-2 p-4`; badge slot; top row `flex items-center gap-3` with icon `flex h-14 w-14 shrink-0 items-center justify-center rounded-icon text-[26px] {tintClass[tint]}`; `<h3 className="text-[15.5px] font-extrabold leading-[1.3]">`; meta `text-[12.5px] text-sub`; priceTag `text-[15px] font-extrabold` (small facts inside get `font-semibold text-sub`); extraMeta same as meta; actions `mt-1 flex gap-2`.
- [ ] **Step 4: Export, verify, commit** — `feat(d02): category tile, bottom nav, listing card`

---

### Task 8: Modal + Toast (only client components)

**Files:**
- Create: `packages/ui/src/components/modal.tsx` (`"use client"`, Radix Dialog)
- Create: `packages/ui/src/components/toast.tsx` (`"use client"`, Radix Toast)
- Modify: `packages/ui/src/index.ts`

**Interfaces:**
- `Modal({ trigger, title, description?, children })` — overlay `bg-ink/50`; panel `rounded-card border border-line bg-card p-5 shadow-lift` centered, `w-[calc(100vw-32px)] max-w-lg`; title `font-display text-xl font-extrabold`; close button ≥44px. No enter animation beyond opacity (reduced-motion safe).
- `ToastProvider({ children })`, `useToast(): { toast(opts: { title; description? }) }` — viewport `fixed bottom-20 right-4 z-[100]`; toast = Card recipe + `shadow-search`.

- [ ] **Step 1: Implement both with Radix primitives, tokens only.**
- [ ] **Step 2: Verify, commit** — `feat(d02): modal and toast (radix, client-only islands)`

---

### Task 9: Composite layout components

**Files:**
- Create: `packages/ui/src/composites/header-stack.tsx`, `pincode-hero.tsx`, `today-strip.tsx`, `category-group.tsx`, `helpline-band.tsx`, `big-cta-tile.tsx`, `type-filter-row.tsx`, `product-card.tsx`, `cert-bar.tsx`, `eco-strip.tsx`, `section.tsx`
- Modify: `packages/ui/src/index.ts`

**Interfaces (all server components):**
- `HeaderStack({ logo, tagline, location?, right?, children? })` — `<header className="bg-header-gradient">`; topbar `mx-auto flex max-w-[1140px] flex-wrap items-center gap-3 px-4 pb-1 pt-3 text-white`; logo `font-display text-[22px] font-extrabold tracking-[-0.02em]` with tagline `block text-[11px] font-semibold opacity-85 mt-[-3px]`; right slot `ml-auto flex items-center gap-2`; children = searchband (`px-4 pb-4 pt-1.5 mx-auto max-w-[1140px]`) or PincodeHero.
- `PincodeHero({ title, subtitle, children })` — `px-4 pb-[22px] pt-[26px] text-center text-white`; h1 `mb-1 font-display text-[clamp(22px,4.5vw,32px)] font-extrabold`; p `mb-4 text-sm opacity-90`.
- `TodayStrip({ children })` grid `grid gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(170px,1fr))]`; `TodayCard({ label, value, sub, alert? })` — `rounded-card border border-line bg-card px-4 py-3.5` / alert: `border-alert-line bg-alert-bg`; label `flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-[.06em] text-sub`; value `mt-[3px] block text-[19px] font-bold`; sub `text-[12.5px] text-sub`.
- `CategoryGroup({ label, children })` — label `mb-2.5 mt-[18px] flex items-center gap-2 text-[13px] font-extrabold uppercase tracking-[.05em] text-sub after:h-px after:flex-1 after:bg-line after:content-['']`; grid `grid gap-2.5 [grid-template-columns:repeat(auto-fill,minmax(96px,1fr))] max-sm:grid-cols-4`.
- `HelplineBand({ icon, title, sub, action })` — `my-5 flex flex-wrap items-center gap-3.5 rounded-band bg-helpband p-[18px] text-white`; action slot = glowing call button: `ml-auto flex min-h-[44px] items-center gap-2 rounded-icon bg-call px-[22px] py-3.5 text-base font-extrabold text-white shadow-callglow`.
- `BigCtaGrid({ children })` `grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(240px,1fr))]`; `BigCtaTile({ icon, title, sub, cta, href, gradient?: "brand"|"gold" })` — `flex flex-col gap-1.5 rounded-band p-5 text-white no-underline` + `bg-cta-gradient`/`bg-gold-gradient`; go pill `mt-2 self-start rounded-pill border border-white/40 bg-white/20 px-[18px] py-[9px] text-[13.5px] font-extrabold text-white tap-target`.
- `TypeFilterRow({ children })` `flex gap-[9px] overflow-x-auto pb-1 pt-3.5`; `TypeFilter({ icon, label, vernacular?, active? })` — `flex min-w-[86px] shrink-0 flex-col items-center gap-[3px] rounded-card border-2 border-line bg-card px-3.5 py-2.5` active: `border-brand bg-brand-soft`; icon 26px; label `text-xs font-bold` (+`.vern`).
- `ProductGrid({ children })` `grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(160px,1fr))]`; `ProductCard({ image, tint, cert, title, brandLine, cta })` — `flex flex-col overflow-hidden rounded-card border border-line bg-card`; image `flex h-[110px] items-center justify-center text-[44px] {tintClass[tint]}`; body `flex flex-1 flex-col gap-[5px] p-3`; title `text-[13.5px] font-extrabold leading-[1.3]`; brandLine `text-[11.5px] text-sub`; cta = full-width brand button `mt-auto min-h-[44px] rounded-[10px] bg-brand p-2.5 text-center text-[12.5px] font-extrabold text-white`.
- `CertBar({ children })` `flex gap-2.5 overflow-x-auto pb-1.5`; `CertCard({ icon, title, sub, gold? })` — `flex min-w-[230px] shrink-0 items-center gap-2.5 rounded-icon border-[1.5px] border-line bg-card px-4 py-3` gold: `border-certgold-line bg-certgold-bg`.
- `EcoStrip({ children })` `flex gap-2.5 overflow-x-auto pb-4 pt-1`; `EcoPill({ title, sub, href, gradient: "milk"|"organic"|"coins" })` — `min-w-[210px] shrink-0 rounded-card px-[18px] py-3.5 text-white no-underline` + `bg-eco-*`; title `block font-display text-[17px] font-extrabold`; sub `text-xs opacity-90`.
- `Section({ title, see?, seeHref?, children })` — `.sec` py; heading row `mb-3.5 flex items-baseline justify-between gap-2.5`; h2 `font-display text-xl font-extrabold`; see link `text-[13px] font-bold text-brand-deep no-underline`. Plus `CardsRow({ children })` `grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(250px,1fr))]` and `Wrap({ children })` `mx-auto max-w-[1140px] px-4`.

- [ ] **Step 1: Implement all files per recipes above** (tint classes come from `tintClass` in Task 7).
- [ ] **Step 2: Export, verify, commit** — `feat(d02): composite patterns - header stack, hero, strips, bands, grids`

---

### Task 10: i18n — catalogs + next-intl in all 5 apps

**Files:**
- Create: `packages/ui/src/i18n/index.ts`, `packages/ui/src/i18n/messages/en.json`, `ta.json`, `hi.json`
- Modify: `packages/ui/package.json` (`"./i18n": "./src/i18n/index.ts"`)
- Modify: all 5 apps — `package.json` (add `next-intl`), `next.config.ts` (wrap with `createNextIntlPlugin("./i18n/request.ts")`), create `i18n/request.ts`, wrap layout body children in `NextIntlClientProvider`.

**Interfaces:**
- `locales = ["en","ta","hi"] as const`, `type Locale`, `isLocale(x): x is Locale`, `getUiMessages(locale): Record<string, unknown>`.
- Catalog namespace `ui` with keys: `search.placeholder`, `search.hint`, `pincode.title`, `pincode.subtitle`, `pincode.find`, `pincode.gps`, `pincode.inputLabel`, `nav.home`, `nav.categories`, `nav.askAi`, `nav.alerts`, `nav.profile`, `actions.call`, `actions.whatsapp`, `actions.compare`, `badges.verified`, `badges.certVerified`, `product.whereToBuy`, `helpline.title`, `helpline.sub`, `helpline.call`, `today.title`, `lang.label`. Tamil/Hindi values copied from the mockup where present (வேளாண்மை, என் இடம், தேவையை சொல்லுங்கள், कृषि, दूध …), translated in-register otherwise.
- App request config:

```ts
import { getRequestConfig } from "next-intl/server";
import { getUiMessages, isLocale } from "@agri/ui/i18n";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = requested && isLocale(requested) ? requested : "en";
  return { locale, messages: getUiMessages(locale) };
});
```

- [ ] **Step 1: Write catalogs + index; wire the 5 apps; `pnpm add next-intl` per app.**
- [ ] **Step 2: Verify** — `pnpm build` (all apps) PASS; commit — `feat(d02): next-intl in all five apps with en/ta/hi component catalogs`

---

### Task 11: SEO primitives (server-only)

**Files:**
- Create: `packages/ui/src/seo/json-ld.tsx`, `packages/ui/src/seo/meta.ts`, `packages/ui/src/seo/no-index.tsx`, `packages/ui/src/seo/index.ts`, `packages/ui/src/seo/jsonld.typetest.ts`
- Modify: `packages/ui/package.json` (`"./seo": "./src/seo/index.ts"`)

**Interfaces:**
- `JsonLd<T extends Thing>({ data: WithContext<T> })` — renders `<script type="application/ld+json">` with `<`-escaped JSON.
- Builders (each takes a narrow required-fields input, returns `WithContext<…>` — invalid shapes fail typecheck): `localBusinessJsonLd({ name, url, telephone?, address: { locality, region, postalCode? }, geo?, aggregateRating? })`, `productJsonLd({ name, url, brand?, image?, offers?: { price, priceCurrency } , aggregateRating? })`, `faqPageJsonLd({ questions: { question, answer }[] })`, `breadcrumbJsonLd(items: readonly { name: string; url: string }[])`, `datasetJsonLd({ name, description, url, license? })`.
- `buildMetadata({ title, description, canonical, siteName?, noIndex?, ogImage? }): Metadata` (next's type).
- `canonicalUrl(base: string, path: string): string` — strips trailing slash + query, joins safely.
- `NoIndex()` — `<meta name="robots" content="noindex, follow" />` (React 19 hoists to head).
- `shouldNoIndex(contentCount: number, minimum = 1): boolean` — the schedule's "noindex-until-populated" rule.
- `jsonld.typetest.ts` — compile-time assertions with `@ts-expect-error` (e.g. Product with `price: number` object missing `priceCurrency`, breadcrumb item missing `url`).

- [ ] **Step 1: Implement; grep to prove zero `"use client"` under `src/seo/`.**
- [ ] **Step 2: Verify (`pnpm typecheck` — typetest compiles, expect-errors hold), commit** — `feat(d02): typed seo primitives - jsonld builders, metabuilder, noindex`

---

### Task 12: Demo route in web-agri

**Files:**
- Create: `apps/web-agri/app/demo/page.tsx` (server), `apps/web-agri/app/demo/sections.tsx` (server helpers)
- Test: manual — `pnpm --filter @agri/web-agri dev`, open `/demo?theme=agri|milk|organic`

**Interfaces:**
- URL contract consumed by Task 13: `/demo?theme={agri|milk|organic}` (default agri). Theme applied via `<div data-theme={"theme-" + theme}>` wrapper; switcher = three `<a>` styled as TypeFilter chips (server-rendered, keyboard operable).
- Page metadata via `buildMetadata({ …, noIndex: true })` — dogfoods Task 11.
- Content: (1) token board — theme swatches, radii, shadows, type specimen; (2) all 18 components, labeled; (3) all 10 composites arranged like the mockup homes (agri: header stack + searchband, today strip, 5 category groups w/ mockup tiles + real vernacular, helpline, listing cards incl. sponsored/verified, eco strip, bottom nav; milk variant: pincode hero + type filters; organic variant: cert bar + product grid + gold CTA); (4) locale block — CategoryTile grid + key CTAs rendered 3× via `getTranslations({ locale })` for en/ta/hi.
- `searchParams` is a Promise in Next 15 — `const { theme } = await searchParams`.

- [ ] **Step 1: Build the page.** Emoji/labels/tints copied verbatim from `preview_frontend.html` (they are the fixture data).
- [ ] **Step 2: Verify** — dev server renders all three themes without hydration errors; tab-through: every interactive element focusable with visible 3px accent ring; `pnpm check:hex` still green (demo uses tokens only).
- [ ] **Step 3: Commit** — `feat(d02): demo route - full kit per theme and locale`

---

### Task 13: Baseline screenshots + Lighthouse a11y + side-by-side check

**Files:**
- Create: `scripts/capture-baseline.mjs`
- Create: `docs/design-reference/baseline/demo-{agri,milk,organic}.png` (outputs, committed)
- Modify: root `package.json` (devDep `playwright`; script `"baseline": "node scripts/capture-baseline.mjs"`)

- [ ] **Step 1: Script** — playwright chromium, viewport 1280×900, `goto http://localhost:3002/demo?theme=X`, `waitUntil: "networkidle"`, full-page PNG per theme into `docs/design-reference/baseline/`.
- [ ] **Step 2: Run** — `pnpm --filter @agri/web-agri build && pnpm --filter @agri/web-agri start` (background), `pnpm exec playwright install chromium`, `pnpm baseline`.
- [ ] **Step 3: Side-by-side against the mockup** — open `preview_frontend.html` screenshots at same width; compare header stack, category tiles, listing cards, helpline, bottom nav, pincode hero, product cards, cert bar per theme. Fix any drift (this is the spec's core bar), re-capture.
- [ ] **Step 4: Lighthouse** — `pnpm dlx lighthouse http://localhost:3002/demo --only-categories=accessibility --chrome-flags="--headless=new" --output=json` (CHROME_PATH → playwright chromium if needed). Require ≥95; fix and re-run otherwise.
- [ ] **Step 5: Commit** — `test(d02): visual-regression baseline screenshots per theme`

---

### Task 14: Final verification + PR

- [ ] **Step 1:** `pnpm lint && pnpm typecheck && pnpm build && pnpm check:hex` — all green.
- [ ] **Step 2:** Re-read SPEC D02 DO/DON'T/NON-NEGOTIABLES against the diff (superpowers:verification-before-completion).
- [ ] **Step 3:** Push branch, open PR → `dev` titled `feat(d02): design system per spec v1`, body summarizing tokens/components/composites/i18n/seo/demo + baseline screenshots + Lighthouse score. Never target main.

---

## Self-Review (done at plan time)

- **Spec coverage:** A→Task 1, hex-ban→2, B fonts→3, C shadcn+18 components→4–8, D composites→9, E i18n→10, F SEO→11, G demo+screenshots→12–13, DoD checks→13–14. `.vern`/focus/tap-target in Task 1. Sponsored-always-labeled enforced by Badge's type. CLS-0 skeleton via required dims.
- **Assumptions to confirm:** both resolved in-repo (design-system.md §4 emoji official; §1.1 + `SiteTheme` type = data-theme switching) — noted in PR body, no user blocking needed.
- **Known risks:** next/font inside transpiled package (works on Next 15; fallback = per-app font files), `getTranslations({locale})` override (fallback = read catalogs directly via `getUiMessages`), `color-mix` in shadow-ai (baseline browsers OK).
