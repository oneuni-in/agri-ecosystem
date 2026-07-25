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
