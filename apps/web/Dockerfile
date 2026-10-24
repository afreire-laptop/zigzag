# syntax=docker/dockerfile:1
# zigzag web app: the Vite build served by unprivileged nginx. Build from the repository root:
#   docker build -f apps/web/Dockerfile .
ARG NODE_IMAGE=node:24.21.0-trixie-slim
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.30.5-alpine

FROM ${NODE_IMAGE} AS build
ENV CI=true
RUN npm install --global --no-fund --no-audit pnpm@12.9.1
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY apps/api/package.json apps/api/
COPY packages/api-client/package.json packages/api-client/
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile --filter "@zigzag/web..."
COPY tsconfig.base.json ./
COPY packages/api-client packages/api-client
COPY apps/web apps/web
RUN pnpm --filter @zigzag/web run build

FROM ${NGINX_IMAGE} AS runtime
COPY apps/web/nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY apps/web/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/healthz"]
