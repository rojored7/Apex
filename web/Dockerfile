# Imagen del front de APEX (US-006). Contexto de build: la raíz del repositorio
# (necesita infra/nginx/default.conf). Etapa build con Node, etapa final con Nginx
# que solo contiene el build estático y la configuración.
#
# Hasta US-009 no existe web/package.json: se sirve web/index.html provisional.
# US-009 deja el build real (npm ci && npm run build) y quita la rama provisional.

FROM node:22-alpine AS build
WORKDIR /web
COPY web/ ./
RUN if [ -f package.json ]; then \
      npm ci && npm run build; \
    else \
      mkdir -p dist && cp index.html dist/index.html; \
    fi

FROM nginx:stable-alpine
COPY --from=build /web/dist /usr/share/nginx/html
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
