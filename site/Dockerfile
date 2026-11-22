# syntax=docker/dockerfile:1

# Bau Stage
# renovate: datasource=github-releases depName=gohugoio/hugo
ARG HUGO_VERSION=0.170.1

FROM node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bfd3d99a554bfd9adeea09ea8017f6e85f5 AS build
ARG HUGO_VERSION

# Ab Hugo 0.170.0 gibt es nur noch ein Binary ("extended" ist als Alias entfallen).
RUN apk add --no-cache go git curl tar \
 && curl -fsSL -o /tmp/hugo.tgz "https://github.com/gohugoio/hugo/releases/download/v${HUGO_VERSION}/hugo_${HUGO_VERSION}_linux-amd64.tar.gz" \
 && tar -xzf /tmp/hugo.tgz -C /usr/local/bin \
 && rm /tmp/hugo.tgz \
 && hugo version \
 && corepack enable
# pnpm-Version kommt allein aus dem packageManager-Feld in package.json (corepack).

WORKDIR /src
# hugo findet tailwindcss nur über PATH
ENV PATH="/src/node_modules/.bin:${PATH}"

COPY go.mod go.sum package.json pnpm-lock.yaml .npmrc ./
RUN hugo mod tidy \
 && go mod download \
 && pnpm install --frozen-lockfile

COPY . .
RUN hugo --minify

# Letzte Stage
FROM nginx/nginx-unprivileged:1.30-alpine@sha256:0c53a1f2890c3526bfd201440f0fd3970e5b78f80630f58284aad0d34b5ec7bd
# Base-Image-Tag ist floating — apk upgrade holt gefixte OS-Pakete (z.B. libxml2)
# aus dem Alpine-Repo, auch wenn nginx das Base-Image nicht neu gebaut hat.
# https://avd.aquasec.com/nvd/2026/cve-2026-86144/

USER root
RUN apk upgrade --no-cache

USER nginx
COPY --from=build /src/public/ /usr/share/nginx/html/
EXPOSE 8080
