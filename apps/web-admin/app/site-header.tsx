import { AuthCluster } from "@agri/auth-client/react";
import { HeaderStack } from "@agri/ui";

export function SiteHeader() {
  return <HeaderStack logo="Agri Admin" tagline="internal" right={<AuthCluster />} />;
}
