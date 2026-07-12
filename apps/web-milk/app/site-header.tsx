import { AuthCluster } from "@agri/auth-client/react";
import { HeaderStack, LocationPill } from "@agri/ui";

export function SiteHeader() {
  return (
    <HeaderStack
      logo={
        <>
          Milk<span className="text-accent">.in</span>
        </>
      }
      tagline="Pincode-first dairy discovery"
      location={<LocationPill>📍 Set location</LocationPill>}
      right={<AuthCluster />}
    />
  );
}
