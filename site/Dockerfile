# Bau Stage
ARG HUGO_VERSION=0.170.0
# Muss zur packageManager-Angabe in package.json und zum pnpm-lock.yaml passen!
ARG PNPM_VERSION=10.14.0

FROM node:24-alpine AS build
ARG HUGO_VERSION
ARG PNPM_VERSION

RUN apk add --no-cache go git curl tar \
 && curl -fsSL -o /tmp/hugo.tgz "https://github.com/gohugoio/hugo/releases/download/v${HUGO_VERSION}/hugo_extended_${HUGO_VERSION}_linux-amd64.tar.gz" \
 && tar -xzf /tmp/hugo.tgz -C /usr/local/bin \
 && rm /tmp/hugo.tgz \
 && hugo version \
 && corepack enable \
 && corepack prepare pnpm@${PNPM_VERSION} --activate

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
FROM nginxinc/nginx-unprivileged:1.30-alpine
COPY --from=build /src/public/ /usr/share/nginx/html/
EXPOSE 8080
