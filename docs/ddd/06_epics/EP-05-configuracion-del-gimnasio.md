# EP-05 · Configuración del gimnasio

- **Versión del plan:** v0.1 (supuesto S6; `BRECHAS.md` sección 2, "Módulo settings"). Las secciones nuevas se agregan en la versión que las necesita.
- **Bounded context:** Settings (soporte, esquema `settings`).
- **Estimación relativa:** S.

## Objetivo de negocio

Que el dueño ajuste los datos de su gimnasio desde una pantalla, sin pedirle a nadie que toque archivos: nombre y datos del box, horas, etiquetas de los medios de pago, canales de aviso, valores por defecto de clases y membresías, el token de la TV y la versión vigente de la política de privacidad.

## Actores

- Administrador: único que lee y edita la configuración.
- Módulos consumidores (Conformist): Payments (medios), Notifications (canales), Classes (horas, cupo por defecto), TV (token), Members (versión de la política de privacidad).

## Capacidades incluidas

### Backend
- Aggregate `SettingsSection` con `key` (`gym`, `hours`, `payment_methods`, `channels`, `classes`, `memberships`, `tv`, `privacy`), `value` JSON validado por un esquema Pydantic por sección y `version`; auditado.
- `get_section`, `update_section` con `settings.validate_section` como función pura.
- `payment_methods()` devuelve el enum fijo de v0.1 (`cash`, `nequi`, `breb`, supuesto S8) decorado con las etiquetas de la sección.
- `tv.regenerate_token`: el token se genera, nunca se escribe a mano.
- Endpoints solo admin: `GET /settings/{section}`, `PATCH /settings/{section}`, `POST /settings/tv/regenerate-token`.
- En v0.1 solo se validan con contenido real las secciones `gym`, `payment_methods` y `privacy`; `channels`, `classes` y `tv` se activan con sus épicas (EP-14, EP-21, EP-23).

### Front
- Pantalla de configuración con una pestaña por sección, formularios con React Hook Form + Zod y guardado por sección.

## Fuera de alcance

- Medios de pago configurables como lista libre (S8: se agregan con migración si el gimnasio pide otro).
- Credenciales de canales de aviso reales (EP-14).
- Varias sedes (fuera de alcance v1.0).

## Criterios de éxito medibles

- Una sección con un valor que no cumple su esquema devuelve 422 con `field`.
- Cada cambio de sección deja una fila en auditoría con antes y después.
- Regenerar el token de TV invalida el anterior de inmediato (prueba cuando exista EP-23).
- Un coach recibe 403 en todas las rutas de settings.

## Dependencias

- EP-01 Núcleo compartido.
- EP-03 Seguridad de la plataforma (rol admin).
- EP-06 Layout y componentes compartidos del front.

## Riesgos

- Que las secciones crezcan sin dueño y se vuelvan un cajón de sastre; cada sección nueva debe nombrar la épica que la consume.
- Ambigüedad de lo que contienen `memberships` y `classes` (ver preguntas abiertas del README).
- Las credenciales de canales en JSON auditado podrían quedar en claro en la auditoría; hay que decidir si van por `.env` o por el bus.

## Pantallas del diseño que habilita

- `Config` (secciones gimnasio, medios de pago y privacidad en v0.1; el resto se completa por versión).
