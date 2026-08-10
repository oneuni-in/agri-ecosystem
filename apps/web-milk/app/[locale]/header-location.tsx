"use client";

/**
 * Header location switcher (D19 Task 9). Thin wrapper around
 * `LiveLocationPill` (D19 Task 8, `@agri/ui`): that component has no
 * next-intl dependency, so this wrapper builds its `strings` from
 * `useTranslations("ui.location")` (same precedent as
 * `notifications-client.tsx`) and supplies `isAuthed` from `useAgriUser`.
 *
 * `autoSilentSso: false` because `AuthCluster` (rendered as a header
 * sibling) already runs `useAgriUser()` and owns the silent-SSO probe for
 * this page load - this component must not trigger a second one.
 *
 * This is the ONE location switcher in the header (D19 NN#3) - it replaces
 * the hardcoded static `LocationPill` that used to live in `site-header.tsx`.
 */
import { useAgriUser } from "@agri/auth-client/react";
import { LiveLocationPill } from "@agri/ui";
import { useTranslations } from "next-intl";

export function HeaderLocation() {
  const { status } = useAgriUser({ autoSilentSso: false });
  const t = useTranslations("ui.location");
  return (
    <LiveLocationPill
      // U1 §2: on milk.in's flat header the location control is plain text
      // (`.loc{color:var(--mk-soft)}`), not a glass pill. That is also what
      // fixes its contrast: white on the glass overlay measures 4.34:1 over
      // the flat --brand fill (axe `color-contrast`, under the 4.5:1 floor),
      // while --brand-soft directly on --brand is 7.4:1.
      className="border-transparent bg-transparent text-brand-soft"
      isAuthed={status === "authenticated"}
      strings={{
        set: t("set"),
        title: t("title"),
        close: t("close"),
        apply: t("apply"),
        gps: t("gps"),
        pincodeLabel: t("pincodeLabel"),
        find: t("find"),
      }}
    />
  );
}
