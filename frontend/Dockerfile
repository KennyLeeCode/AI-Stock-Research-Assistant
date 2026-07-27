# syntax=docker/dockerfile:1

# =============================================================================
# Stage 1 - build
#
# Node, the toolchain, and node_modules exist only here. None of it reaches the
# final image, which ships static files and a web server.
# =============================================================================
FROM node:24-alpine AS build

WORKDIR /app

# `npm ci` installs exactly what the lockfile pins, which is what makes a build
# reproducible. It also requires the lockfile to be in sync with package.json
# and fails loudly if it is not - better than `npm install` silently resolving
# to different versions than were tested.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# VITE_API_BASE_URL is deliberately left empty. Vite inlines every VITE_*
# variable into the public bundle at build time, so a value here would be
# baked in and readable by anyone. Empty means the app makes same-origin
# requests to /api, which nginx proxies to the backend below - no host to
# configure, and no opportunity to leak one.
ENV VITE_API_BASE_URL=""

RUN npm run build

# =============================================================================
# Stage 2 - serve
#
# nginx-unprivileged rather than the standard nginx image: the stock image runs
# its master process as root. This one runs entirely as UID 101 and listens on
# 8080, so no capability to bind a privileged port is needed.
# =============================================================================
FROM nginxinc/nginx-unprivileged:1.29-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:8080/ || exit 1
