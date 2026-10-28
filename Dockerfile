# ---- build stage -----------------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY . .
# Mocks must be off in production builds.
ARG VITE_USE_MOCKS=false
ENV VITE_USE_MOCKS=$VITE_USE_MOCKS
RUN npm run typecheck && npm run lint && npm run build

# ---- serve stage -----------------------------------------------------------
FROM nginx:1.27-alpine AS serve
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null || exit 1
CMD ["nginx", "-g", "daemon off;"]
