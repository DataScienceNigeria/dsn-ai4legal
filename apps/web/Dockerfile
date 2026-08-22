FROM node:22-alpine AS deps
WORKDIR /srv
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /srv
COPY --from=deps /srv/node_modules ./node_modules
COPY . .

# Next inlines NEXT_PUBLIC_ values at build time, so the browser-facing API
# address has to be known here rather than at run time.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /srv
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=build /srv/node_modules ./node_modules
COPY --from=build /srv/.next ./.next
COPY --from=build /srv/public ./public
COPY --from=build /srv/package.json ./package.json

RUN addgroup -g 10001 web && adduser -u 10001 -G web -D web \
    && chown -R web:web /srv
USER web

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD wget -qO- http://127.0.0.1:3000/sign-in > /dev/null || exit 1

CMD ["npx", "next", "start", "-p", "3000", "-H", "0.0.0.0"]
