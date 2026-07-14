import { AuthCluster } from "@agri/auth-client/react";
import { CoinsBalancePill, HeaderStack, LocationPill } from "@agri/ui";

export function SiteHeader() {
  return (
    <HeaderStack
      logo="organicstore.in"
      tagline="Trusted organic · இயற்கை · जैविक"
      location={
        <LocationPill>
          📍 <span className="max-sm:hidden">Coimbatore</span> ▾
        </LocationPill>
      }
      right={
        <>
          <CoinsBalancePill endpoint="/api/coins/balance" />
          <AuthCluster />
        </>
      }
    />
  );
}
