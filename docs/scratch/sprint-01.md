# Cuaderno · Sprint 1 · Núcleo de auditoría, bus de criptografía y seguridad

Rama `feat/sprint-01-nucleo-cripto-seguridad`, creada desde `main` el 2026-10-21 tras el
merge local (fast-forward) de `chore/sprint-00-cimientos` (`ca8415f`). El push a GitHub
lo bloquea el clasificador de permisos de la sesión: queda como paso humano.

## Línea base (2026-10-21)

- `git status` limpio en `main` = `ca8415f`.
- api: 106 pruebas en verde, 1 saltada; cobertura 93 % (cierre del Sprint 0).
- web: 75 pruebas en verde; cobertura 100 %.
- Stack de desarrollo arriba: `apex-db-1`, `apex-db_test-1`, `apex-api-1`, `apex-web-1`
  en los puertos 8180/8181/5442/5443 (`.env` local).

## Slices

### S1-W0-1 · Cabeceras de seguridad y CSP con nonce (US-038)

- Rojo: `web/tests/unit/index-html.test.ts` (2 de 5 fallaban: sin `nonce` en `<script>` y `<link>`),
  `web/tests/e2e/csp.spec.ts`, `scripts/smoke/headers.sh`.
- Verde: `vite.config.ts` (`html.cspNonce`, `modulePreload.polyfill=false`),
  `infra/nginx/snippets/{security-headers,proxy-api}.conf`, `default.conf` con CSP exacta,
  `sub_filter` de `__CSP_NONCE__` → `$request_id`, `no-store`, `location /api/v1/tv/` (N-44),
  `web/Dockerfile` copia los snippets; `test_nginx_conf.sh` ampliado (26 comprobaciones);
  `compose-smoke.sh` llama a `headers.sh`.
- Evidencia: `headers.sh` contra Nginx real en 8180: 19 ok, 0 fallas (nonces distintos entre
  peticiones, 413 con 6 MB). Playwright `csp.spec.ts`: 2 ok sobre `vite preview` (interceptando
  como Nginx) y 1 ok + 1 saltada con `CSP_BASE_URL=http://localhost:8180/`. `web-smoke.sh` 5/5.
  `slice-gate.sh web/app tests/unit/index-html.test.ts` verde.
- Desviaciones: no hay script de tema inicial, así que T3 (`theme-init.js`) no aplica. El smoke de
  cabeceras corre dentro del job `images` (vía `compose-smoke.sh`), no en un job `smoke-headers`
  aparte: los nombres de los checks obligatorios no cambian. La prueba del HTML construido corre en
  entorno node y construye con la API de Vite a un directorio temporal.
