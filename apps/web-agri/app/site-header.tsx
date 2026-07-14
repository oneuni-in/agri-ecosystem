import { AuthCluster } from "@agri/auth-client/react";
import { CoinsBalancePill, HeaderStack, LocationPill } from "@agri/ui";

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
          <CoinsBalancePill endpoint="/api/coins/balance" />
          <AuthCluster />
        </>
      }
    />
  );
}
