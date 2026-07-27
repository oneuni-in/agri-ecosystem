import createMiddleware from "next-intl/middleware";

import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  // Skip API/BFF proxies, Next internals and any file with an extension
  // (sitemap.xml, favicon, images). Everything else gets locale handling.
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
