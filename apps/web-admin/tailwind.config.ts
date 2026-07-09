import { agriPreset } from "@agri/config/tailwind-preset";
import type { Config } from "tailwindcss";

export default {
  presets: [agriPreset],
  content: [
    "./app/**/*.{ts,tsx}",
    "../../packages/ui/src/**/*.{ts,tsx}",
  ],
} satisfies Config;
