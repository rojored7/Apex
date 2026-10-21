# EP-25 · Portal del socio

- **Versión del plan:** v1.0 (versión 1.0, puntos 1 y 2; `BRECHAS.md` sección 2, "Resultados y portal").
- **Bounded context:** Portal (lectura, módulo `portal`, sin esquema), Conformist de Members, Memberships, Payments, Training, Athletes y Notifications. Toca Auth (Partnership con Members para la cuenta de portal) y Training (resultados `pending` y validación).
- **Estimación relativa:** XL.

## Objetivo de negocio

Que el socio vea su plan, sus pagos y sus marcas sin preguntar (segunda mitad de la frase guía). Menos preguntas en recepción, más confianza del socio en que su plata está bien registrada, y más motivación porque ve su progreso y puede cargar su resultado desde el celular.

## Actores

- Socio: único usuario del portal; solo ve lo suyo (RN-15).
- Administrador: crea o habilita la cuenta de portal del socio.
- Coach y administrador: validan los resultados enviados por los socios.

## Capacidades incluidas

### Backend
- Cuenta de portal: un usuario `member` apunta a un socio (`auth.users.member_id`); se crea desde Members (acción explícita o `MemberCreated`) y Auth la crea con enlace de activación por correo (EP-04 y EP-14).
- Todas las rutas `/me/*` con `require_role("member")` y filtro por el `member_id` del token, delegando en los services de cada contexto.
- `GET /me/summary`, `GET /me/payments`, `GET /me/payments/{id}/receipt.pdf` (sobre EP-16).
- `GET /me/results`, `GET /wods/today` para el socio, `POST /me/results`: el resultado nace `pending` (RN-11).
- `POST /results/{id}/validate` (coach o admin) que emite `WodResultValidated` y alimenta RN-12.
- `GET /me/records`, `GET /me/rms`, `GET /me/benchmarks`, `GET /me/metrics`, `POST /me/metrics`.
- `GET /me`, `PATCH /me` con los campos que el gate defina (nunca el documento), `POST /me/password`.
- `GET /me/notifications`, `PATCH /me/channels`, `POST /me/push-subscription` (activa el `WebPushChannel` de EP-14 para los socios).

### Front
- `PortalLayout` con menú inferior y seis pantallas: inicio, pagos con recibo, WODs con envío de resultado, progreso, datos y cambio de contraseña, avisos y canales.
- En el panel: bandeja o marca de "por validar" en el registro de resultados y en el detalle del WOD.

## Fuera de alcance

- App móvil nativa (el portal es web responsive; PWA opcional).
- Pagos en línea desde el portal.
- Chat o comunidad entre socios.
- Portal para coach que también es socio (P6, v1.1).

## Criterios de éxito medibles

- Un socio que cambia el `member_id` en la URL o en el cuerpo de una petición nunca ve datos de otro socio (prueba de autorización por cada ruta `/me/*`).
- Un resultado enviado por el socio no aparece en el leaderboard hasta que un coach lo valida; al validarlo, si supera su RM, crea el récord derivado.
- `PATCH /me` con el documento devuelve 422.
- El portal es usable en 390 × 844 con controles de 44 px y pasa el chequeo automático de accesibilidad.
- E2E de Playwright: el socio activa su cuenta, entra, ve su plan al día, descarga un recibo y envía un resultado.

## Dependencias

- EP-04 Identidad y acceso (usuario `member`, activación).
- EP-07 Padrón de socios, EP-09 Membresías, EP-10 Pagos (datos del socio).
- EP-14 Avisos de vencimiento (avisos del socio, correo de activación, web push).
- EP-16 Recibos y exportaciones (recibo PDF).
- EP-22 Entrenamiento (WODs y resultados).
- EP-24 Perfil del atleta (récords y medidas).
- EP-20 Acceso cifrado con TLS (para usarlo desde fuera del gimnasio).
- EP-06 Layout y componentes compartidos del front (`PortalLayout`).

## Riesgos

- P5: el correo de login en claro en `auth.users.email`.
- Los campos editables por el socio no están definidos (`BRECHAS.md` sección 2); cada uno es un dato cifrado que el socio modifica y debe auditarse.
- Validar resultados enviados puede convertirse en trabajo pesado para el coach si no hay una bandeja clara.
- Sin dominio con TLS (P7), el portal solo sirve dentro del local.

## Pantallas del diseño que habilita

- `Portal_Inicio`, `Portal_Pagos`, `Portal_WODs`, `Portal_Progreso`, `Portal_Datos`, `Portal_Avisos`; validación de resultados enviados en `Resultados_Registro` y `WOD_Detalle`.
