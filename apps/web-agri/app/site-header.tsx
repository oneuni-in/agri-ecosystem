import { AuthCluster, NotificationBellIsland } from "@agri/auth-client/react";
import { HeaderStack, LocationPill } from "@agri/ui";

export function SiteHeader() {
  return (
    <HeaderStack
      logo="agri.in"
      tagline="All of agriculture · வேளாண்மை · कृषि"
      location={
        <LocationPill>
          📍 <span className="max-sm:hidden">Coimbatore · 641001</span> ▾
        </LocationPill>
      }
      right={
        <>
          <NotificationBellIsland basePath="/api/notify" href="/notifications" label="Notifications" />
          <AuthCluster />
        </>
      }
    />
  );
}
