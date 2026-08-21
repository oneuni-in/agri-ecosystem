# Shared image for all Next.js apps (SPEC D04-D). Build from the REPO ROOT:
#
#   docker build -f apps/Dockerfile --build-arg APP=web-agri -t agri-web-agri .
#
# Every app image listens on 3000; compose maps external ports.
FROM node:24-alpine AS builder

# pinned to packageManager in package.json
RUN npm install -g pnpm@11.10.0
WORKDIR /repo
COPY . .
RUN pnpm install --frozen-lockfile

ARG APP
# NEXT_OUTPUT switches next.config.ts to standalone output (kept off for
# local/CI builds - symlink tracing breaks on Windows dev boxes)
ENV NEXT_OUTPUT=standalone
# release tag for sentry (set by deploy-staging.yml), and the Business
# Console origin web-milk's ListBusinessCta links to (Task 11 fix round 2,
# sourced from the `NEXT_PUBLIC_CONSOLE_URL` repo variable — see
# docs/runbooks/staging-deploy.md). Both are NEXT_PUBLIC_ vars, inlined at
# build time, so they must exist in the builder stage. Defaulting
# CONSOLE_URL to "" is deliberate: apps that don't import
# apps/web-milk/lib/console.ts (web-organic, web-agri, web-id, web-admin)
# never read NEXT_PUBLIC_CONSOLE_URL and are unaffected either way; web-milk
# itself fails loudly at build time if it's empty in production (see
# apps/web-milk/lib/console.ts) rather than silently inlining a blank/wrong
# origin — no hostname is invented here.
#
# VAPID_PUBLIC_KEY is the third of these, and the reason it exists: web push
# was fully built and CI-verified, yet dead in every container image, because
# NEXT_PUBLIC_VAPID_PUBLIC_KEY had no way to reach the builder. lib/push.ts
# reads it at MODULE level, so an empty value makes PUSH_CONFIGURED false and
# detectPushState() answer "unsupported" — the UI renders nothing and no error
# is raised anywhere. Setting it in the container's runtime environment does
# not help: NEXT_PUBLIC_ vars are inlined into the bundle during `next build`,
# which has already happened by then.
#
# The public half is safe here. It ships to every browser as the subscription
# applicationServerKey by design, which is also why it comes from a repo
# VARIABLE rather than a secret, exactly like CONSOLE_URL. The PRIVATE key is
# never a build arg — the backend signs with it at runtime and reads it from
# sops (docs/runbooks/web-push.md).
#
# Defaulting to "" keeps the current behaviour for any build that does not
# pass it: push stays dark, which is the honest state when no key exists.
ARG GIT_SHA=""
ARG CONSOLE_URL=""
ARG VAPID_PUBLIC_KEY=""
ENV NEXT_PUBLIC_RELEASE=$GIT_SHA
ENV NEXT_PUBLIC_CONSOLE_URL=$CONSOLE_URL
ENV NEXT_PUBLIC_VAPID_PUBLIC_KEY=$VAPID_PUBLIC_KEY
RUN pnpm exec turbo run build --filter=@agri/${APP}

FROM node:24-alpine AS runner

RUN addgroup -S app && adduser -S app -G app
WORKDIR /app
ARG APP
ARG GIT_SHA=""
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    APP=${APP} \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    RELEASE=${GIT_SHA}

# standalone output is rooted at the monorepo root (outputFileTracingRoot),
# so server.js lives at apps/<APP>/server.js inside the bundle
COPY --from=builder /repo/apps/${APP}/.next/standalone ./
COPY --from=builder /repo/apps/${APP}/.next/static ./apps/${APP}/.next/static

USER app
EXPOSE 3000
# exec so node is PID 1 and receives SIGTERM from compose (fast, clean stops);
# shell indirection is needed because APP is only known at runtime via ENV
CMD ["sh", "-c", "exec node apps/${APP}/server.js"]
