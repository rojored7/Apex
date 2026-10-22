# Imagen del front de APEX (US-006, US-009). Contexto de build: la raíz del repositorio
# (necesita infra/nginx/default.conf). Etapa build con Node, etapa final con Nginx
# que solo contiene el build estático y la configuración.

# node:22-alpine por digest (2026-10-22, S3-D62); renovar (docs/RUNBOOK.md §7):
# docker buildx imagetools inspect node:22-alpine --format '{{json .Manifest.Digest}}'
FROM node:22-alpine@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914 AS build
WORKDIR /web
# Primero el manifiesto y el lock: la capa de npm ci se reutiliza si no cambian.
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# nginx:stable-alpine por digest (2026-10-22, S3-D62; el mismo de scripts/ci/test_nginx_conf.sh);
# renovar: docker buildx imagetools inspect nginx:stable-alpine --format '{{json .Manifest.Digest}}'
FROM nginx:stable-alpine@sha256:47928bf67eb62a1863cb08d9ecb52d3e704304ba614eaee17884204677702951
COPY --from=build /web/dist /usr/share/nginx/html
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY infra/nginx/snippets/ /etc/nginx/snippets/
EXPOSE 80
