# Imagen del front de APEX (US-006, US-009). Contexto de build: la raíz del repositorio
# (necesita infra/nginx/default.conf). Etapa build con Node, etapa final con Nginx
# que solo contiene el build estático y la configuración.

FROM node:22-alpine AS build
WORKDIR /web
# Primero el manifiesto y el lock: la capa de npm ci se reutiliza si no cambian.
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM nginx:stable-alpine
COPY --from=build /web/dist /usr/share/nginx/html
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY infra/nginx/snippets/ /etc/nginx/snippets/
EXPOSE 80
