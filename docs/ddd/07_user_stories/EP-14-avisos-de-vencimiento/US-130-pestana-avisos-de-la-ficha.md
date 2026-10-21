# US-130 · Como coach quiero ver en la ficha del socio los avisos que se le han enviado para saber si ya se le recordó antes de hablarle

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** Notifications (lectura), en la ficha de Members
- **Versión:** v0.2
- **Actor:** administrador, coach
- **Tamaño:** 2
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Socio_Ficha` (`/socios/:id`, pestaña Avisos)

## Historia

Como coach o administrador
quiero una pestaña Avisos en la ficha con los avisos del socio y sus canales
para tener todo su contexto de recordatorios en un solo lugar

## Contexto de dominio

- **Aggregate / entidades:** `Notification` (lectura), `MemberChannelPreference` (bloque de US-123).
- **Reglas que aplica:** paginación; RN-13 (sin contacto en claro).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** reutiliza `GET /notifications?member_id=`; alias `GET /members/{id}/notifications` según `ROUTES.md`.
- **Front:** pestaña Avisos con lista paginada y el bloque de canales de US-123.

## Criterios de aceptación

1. `GET /api/v1/members/{id}/notifications` devuelve los avisos del socio con la misma forma y paginación (`limit`/`offset`, máx. 200) que `GET /notifications`; el `member_id` lo fija la ruta.
2. Un socio inexistente responde 404; uno dado de baja muestra su historial (los avisos no se borran).
3. La pestaña muestra fecha objetivo, regla, canal, estado con texto y quién envió u omitió; nunca teléfono ni correo.
4. Admin y coach acceden; un socio recibe 403.
5. La pestaña se carga solo al abrirla (no en la carga inicial de la ficha).

## Escenarios BDD

```gherkin
# language: es
Característica: Pestaña Avisos de la ficha

  Escenario: Ver los avisos de un socio
    Dado que inicié sesión como coach
    Y Juan Ríos tiene un aviso enviado por WhatsApp y uno omitido
    Cuando abro la pestaña Avisos de su ficha
    Entonces veo los dos avisos con su estado y quién los gestionó

  Escenario: Socio inexistente
    Dado que inicié sesión como administrador
    Cuando pido los avisos de un socio que no existe
    Entonces la respuesta es 404
```

## Endpoints

- `GET /api/v1/members/{id}/notifications` — rol(es): admin, coach — entrada: `limit`, `offset`, `status` — códigos: 200, 401, 403, 404, 422

## Pantalla

- `Socio_Ficha`, pestaña Avisos: `DataTable` compacta y bloque Canales (US-123); vacío "Sin avisos todavía".

## Notas técnicas

- **Migración:** no.
- **Pruebas:** router (404, 403, filtro forzado por ruta); Vitest de la pestaña con carga diferida.
- **Archivos principales:** `api/src/app/modules/notifications/router.py`, `web/src/features/members/tabs/NotificationsTab.tsx`.
- El router vive en `notifications` (dueño de los datos) aunque la ruta cuelgue de `/members`.

## Supuestos

- Supuesto: la ruta `/members/{id}/notifications` existe como alias; `ROUTES.md` la nombra como pestaña pero el contrato no la define.

## Dependencias

- US-129 · Historial de envíos
- US-073 · Ver ficha del socio

## INVEST

- **Independiente:** reutiliza el listado.
- **Negociable:** columnas.
- **Valiosa:** contexto rápido en la ficha.
- **Estimable:** pequeña.
- **Pequeña:** 2.
- **Testeable:** filtro por socio verificable.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de router en verde; cobertura de 80 % o más en lo tocado
- [ ] Front: prueba de la pestaña; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
