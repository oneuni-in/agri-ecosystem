import { createAgriAuth } from "@agri/auth-client";

/** Dev defaults line up with migration 0009's seeded redirect URIs and the
 * web-id dev server; prod overrides all four via env (see
 * packages/auth-client/README.md for the domain map). */
export const auth = createAgriAuth({
  clientId: "web-milk",
  appOrigin: process.env.APP_ORIGIN ?? "http://localhost:3000",
  idPublicOrigin: process.env.ID_PUBLIC_ORIGIN ?? "http://localhost:3003",
  idInternalOrigin: process.env.API_BASE_URL ?? "http://127.0.0.1:8000",
  ...(process.env.AUTH_SESSION_SECRET
    ? { sessionSecret: process.env.AUTH_SESSION_SECRET }
    : {}),
});
