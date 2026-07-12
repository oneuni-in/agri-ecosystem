import { createAgriAuth } from "@agri/auth-client";

/** Dev defaults line up with migration 0009's seeded redirect URIs and the
 * web-id dev server; prod overrides all four via env (see
 * packages/auth-client/README.md for the domain map). Only staff and
 * super_admin roles may hold a session on this app - the BFF handlers
 * enforce it (callback 403, me 403, getServerUser null), not the UI. */
export const auth = createAgriAuth({
  clientId: "web-admin",
  appOrigin: process.env.APP_ORIGIN ?? "http://localhost:3004",
  idPublicOrigin: process.env.ID_PUBLIC_ORIGIN ?? "http://localhost:3003",
  idInternalOrigin: process.env.API_BASE_URL ?? "http://127.0.0.1:8000",
  requiredRoles: ["staff", "super_admin"],
  ...(process.env.AUTH_SESSION_SECRET
    ? { sessionSecret: process.env.AUTH_SESSION_SECRET }
    : {}),
});
