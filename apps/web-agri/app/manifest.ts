import { manifestColors } from "@agri/config/tailwind-preset";
import type { MetadataRoute } from "next";

/**
 * A-U4 W4 — the PWA manifest.
 *
 * A route handler, not a static public/manifest.json, so the theme and icon
 * cannot drift from the design tokens they are copied from: both literals
 * below are checked against preset.js by a test, and a Next route is where
 * they can be read from one place later without moving the file.
 *
 * `display: "standalone"` matters beyond aesthetics on iOS — Safari exposes
 * PushManager ONLY inside an installed app (16.4+), so notifications on
 * iPhone depend on this manifest existing and being installable at all.
 *
 * Scope is the whole origin because the offline shell and the saved/mandi
 * routes all live under it; narrowing scope would leave an installed app
 * navigating out of itself into a browser tab.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Agri.in — all of Indian agriculture",
    short_name: "Agri.in",
    description:
      "Mandi prices, weather, government schemes and verified agri businesses near you — in English, Tamil and Hindi.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    // Read from the preset, not copied from it. A manifest is JSON for the
    // browser's install UI so it cannot use var(--brand) — but importing the
    // literals means a token change moves the installed app's chrome with
    // the site's, instead of leaving it stale until someone notices.
    background_color: manifestColors.background,
    theme_color: manifestColors.theme,
    lang: "en",
    dir: "ltr",
    categories: ["agriculture", "business", "news"],
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "maskable",
      },
    ],
  };
}
