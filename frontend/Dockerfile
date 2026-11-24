# syntax=docker/dockerfile:1.7
#
# IPO Engine web app (Next.js, standalone server). Build context: this directory (frontend/).
#
#   docker build -t ipo-engine-web --build-arg NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 frontend
#
# NEXT_PUBLIC_API_BASE_URL is read by the browser and fixed when the app is built: the address at
# which the *browser* reaches the API. The default suits `docker compose up` on one machine; for any
# other address, build the image with that address.

# node:22-slim (multi-arch index), pinned by digest
ARG NODE_IMAGE=node:22-slim@sha256:be979e5523c76fa4d5ca4ebd3099078f220aa47ec39c48ad5b5df9314debd6eb

FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund

FROM ${NODE_IMAGE} AS build
WORKDIR /app
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM ${NODE_IMAGE} AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app
# The container only runs `node server.js`. The npm, corepack and yarn that ship in the base image
# are never used here and carried the image's HIGH vulnerabilities (Trivy, first CI run).
RUN groupadd --system --gid 10001 web \
    && useradd --system --uid 10001 --gid web --no-create-home --home-dir /nonexistent web \
    && rm -rf /usr/local/lib/node_modules /usr/local/bin/npm /usr/local/bin/npx \
              /usr/local/bin/corepack /usr/local/bin/yarn /usr/local/bin/yarnpkg /opt/yarn-*
# The standalone output holds the server and only the node_modules it needs; static files and
# public/ are not part of it and are copied beside it.
COPY --from=build --chown=10001:10001 /app/.next/standalone ./
COPY --from=build --chown=10001:10001 /app/.next/static ./.next/static
COPY --from=build --chown=10001:10001 /app/public ./public

USER 10001:10001
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD node -e "fetch('http://127.0.0.1:3000/').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["node", "server.js"]
