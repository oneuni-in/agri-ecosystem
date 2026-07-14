import { AuthCluster } from "@agri/auth-client/react";
import { CoinsBalancePill, HeaderStack } from "@agri/ui";

export function SiteHeader() {
  return (
    <HeaderStack
      logo="Agri Admin"
      tagline="internal"
      right={
        <>
          <CoinsBalancePill endpoint="/api/coins/balance" />
          <AuthCluster />
        </>
      }
    />
  );
}
