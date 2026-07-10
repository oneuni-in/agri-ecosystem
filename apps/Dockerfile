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
# release tag for sentry (set by deploy-staging.yml); NEXT_PUBLIC_ vars are
# inlined at build time, so this must exist in the builder stage
ARG GIT_SHA=""
ENV NEXT_PUBLIC_RELEASE=$GIT_SHA
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
