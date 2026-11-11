# TLS

Alcance: perfil `tls` de Compose con Caddy. El resto de la guía llega en W0-4.

## Variables

- `APEX_DOMAIN`: va en `.env`. Forma `host[:puerto]`, sin esquema. Vacío = sin dominio. Un puerto solo se admite con `ALLOW_DOMAIN_PORT=true` y un host `*.localhost`.
- `ALLOW_DOMAIN_PORT`: `false` por defecto. Va en `.env`.
- `APEX_CADDY_IP`, `APEX_TLS_ISSUER` (`internal`), `APEX_ACME_EMAIL`, `APEX_ACME_CA`, `APEX_HSTS_MAX_AGE` (`300`) y `TLS_PORT` (`443`): van en `.env.ops`. Solo las leen Compose y el servicio `caddy`; el api no lee el emisor.
