# EP-07 · Padrón de socios

- **Versión del plan:** v0.1 (Tarea 4, con `sex` y `data_consent_at` del supuesto S7).
- **Bounded context:** Members (negocio, esquema `members`).
- **Estimación relativa:** L.

## Objetivo de negocio

Tener a todos los socios en un solo lugar, buscables por nombre, documento o teléfono en segundos, con sus datos personales cifrados y con cada consulta en claro registrada. Reemplaza el cuaderno y el Excel sin cifrar, que hoy son un riesgo legal (RN-13).

## Actores

- Administrador: crea, edita, da de baja y ve datos en claro.
- Coach: ve, crea y edita; no da de baja (`ROUTES.md`, permisos).
- Módulos que consultan al padrón por su service: Memberships, Classes, Training, Notifications y Portal.

## Capacidades incluidas

### Backend
- Aggregate `Member`: `first_name` y `last_name` en claro (van al leaderboard), `sex` (`f`, `m`, `x` o nulo), `status`, `notes`, `deleted_at`, `data_consent_at`, `data_consent_version`; auditado.
- Value objects cifrados por el bus (EP-02): `Document`, `Phone` y `Email` con índice ciego; `BirthDate` y `EmergencyContact` sin índice.
- Invariantes: documento único entre socios no borrados (por índice ciego); nombre y apellido no vacíos; `data_consent_at` opcional con aviso hasta v0.3.
- `list` con búsqueda `q` normalizada contra `document_idx`, `phone_idx` y `email_idx`, o `ILIKE` en nombre; filtros de estado, `membership_status` y `plan_id` resueltos vía `memberships.service.status_for(ids)`; paginado y ordenable.
- `create` devuelve `existing_id` en el error de documento duplicado, para que el front enlace al registro existente.
- `get` con campos cifrados enmascarados por defecto; `reveal(id, field)` descifra un solo campo y audita `reveal` (evento `SensitiveFieldRevealed`).
- `update`; `deactivate` solo admin (baja lógica, RN-14, `BRECHAS.md` sección 5).
- `contact_for_notification(id, purpose)`, que audita el descifrado con propósito (lo consume EP-14).
- Eventos `MemberCreated`, `MemberUpdated`, `MemberDeactivated`.
- Endpoints: `GET /members`, `POST /members`, `GET /members/{id}`, `PATCH /members/{id}`, `DELETE /members/{id}` (admin), `POST /members/{id}/reveal`.

### Front
- Lista de socios con `FilterBar`, chips de estado ("Al día", "Por vencer", "Vencidos", "Congelados", "Sin membresía", "Dados de baja"), `DataTable` y `Pagination`; versión de celular.
- Formulario de crear y editar (sin foto ni adjuntos en v0.1).
- Ficha del socio con encabezado, `MaskedValue` con botón "mostrar" que llama a `reveal`, modal de baja (solo admin) y el contenedor de pestañas; las pestañas Membresías, Pagos e Historial las llenan EP-09, EP-10 y EP-11.

## Fuera de alcance

- Foto y autorización de datos como adjunto (EP-19).
- Exportación CSV (EP-16).
- Filtro `last_attendance` (EP-21) y pestañas Asistencia, Resultados, Atleta y Avisos (EP-21, EP-22, EP-24, EP-14).
- Importación desde Excel (EP-13).
- Cuenta de portal del socio (EP-25).

## Criterios de éxito medibles

- Prueba de búsqueda por documento sin descifrar la tabla y prueba de que el documento no aparece en claro en la base (criterio de salida de la Tarea 4).
- Buscar `1.020.304` encuentra al socio guardado como `1020304`.
- Crear un socio con un documento ya registrado devuelve 409 con `existing_id`.
- Cada `reveal` deja una fila de auditoría con usuario, campo y socio; una ficha abierta sin `reveal` no deja ninguna.
- La lista responde en menos de 500 ms con 1.000 socios y búsqueda por documento (volumen de `01_product_discovery.md` sección 6).
- E2E de Playwright: crear socio, buscarlo por teléfono y abrir su ficha.

## Dependencias

- EP-02 Bus de criptografía (campos cifrados e índices ciegos).
- EP-04 Identidad y acceso (roles y `created_by`).
- EP-06 Layout y componentes compartidos del front.
- EP-09 Membresías, de forma suave: los chips de estado y el filtro por plan muestran datos reales cuando existe `status_for`.

## Riesgos

- Normalizar mal el índice ciego deja duplicados invisibles; la función de normalización es irreversible una vez haya datos.
- Que el coach vea datos en claro sin necesidad; el rol que puede usar `reveal` no está fijado (ver preguntas abiertas).
- Búsqueda por nombre con `ILIKE` sobre texto en claro es lo único que no pasa por el bus; está bien por diseño, pero no debe extenderse a otros campos.

## Pantallas del diseño que habilita

- `Socios_Lista`, `Socios_Movil`, `Socio_Form` (sin foto ni adjuntos), `Socio_Ficha` (encabezado y contenedor de pestañas).
