# syntax=docker/dockerfile:1

# ---- build: compile the static bundle ---------------------------------------------------------------------------
FROM node:24-alpine@sha256:8a32c8cf649a49915a66e81e7a609223c708d0adabf288ee3f4077d765542f85 AS build
WORKDIR /app

# Copy manifests first so the dependency layer is cached until package*.json changes.
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
RUN npx vite build

# ---- runtime: static files + reverse proxy, no Node -------------------------------------------------------------
# nginx-unprivileged runs as uid/gid 101 and listens on 8080, so it works with a read-only root filesystem when
# /tmp and /etc/nginx/conf.d are writable (pid and temp paths live in /tmp). The stock entrypoint renders every
# /etc/nginx/templates/*.template with envsubst into /etc/nginx/conf.d at start, which is how API_UPSTREAM is applied.
FROM nginxinc/nginx-unprivileged:1.30.6-alpine3.24@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03

# Base images lag behind Alpine security fixes; pull them in at build time so the image scans clean between base
# releases. Needs root, so switch to it for this one step and back to the unprivileged user below.
USER root
RUN apk upgrade --no-cache

# Only substitute our own variables; nginx's own $uri, $host, ... must pass through untouched.
# NGINX_ENTRYPOINT_LOCAL_RESOLVERS makes the entrypoint export NGINX_LOCAL_RESOLVERS (from /etc/resolv.conf), so the
# template can resolve the upstream per request instead of failing to boot when the backend is not up yet.
ENV NGINX_ENVSUBST_FILTER="^(API_UPSTREAM|NGINX_LOCAL_RESOLVERS)$" \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1 \
    API_UPSTREAM=http://backend:8000

COPY nginx/security-headers.conf /etc/nginx/security-headers.conf
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

# Explicit non-root user (the base image already defaults to it; stating it keeps scanners and readers certain).
USER 101

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
