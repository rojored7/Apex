# 03 · Mapa de contextos

Fecha: 21 de octubre de 2026. Entrada: `02_domain_model.md`.

## 1. Bounded contexts

Cada contexto es un módulo de `api/src/app/modules/` con su esquema de PostgreSQL. Los contextos transversales viven en `core/`.

### Contextos de negocio

1. **Members (socios)** — esquema `members`. Aggregate Member, preferencias de canal, suscripciones push. Dueño de los datos personales cifrados. Versión 0.1.
2. **Plans (planes)** — esquema `plans`. Aggregate Plan. Versión 0.1.
3. **Memberships (membresías)** — esquema `memberships`. Aggregate Membership y la operación `sell`. Dueño del estado "al día / por vencer / vencido". Versión 0.1.
4. **Payments (pagos)** — esquema `payments`. Aggregate Payment, inmutable. Versión 0.1.
5. **Classes (clases)** — esquema `classes`. ClassSlot, ClassSession, Attendance. Versión 0.4.
6. **Training (entrenamiento)** — esquemas `wods` y `results`. Movement, Wod, WodResult. Dos módulos en código (`wods`, `results`) que forman un contexto porque comparten lenguaje y cambian juntos. Versión 0.5.
7. **Athletes (atleta)** — esquema `athletes`. BodyMetric, PersonalRecord. Versión 0.6.
8. **Notifications (avisos)** — esquema `notifications`. Rule, Template, Notification, canales. Versión 0.2.

### Contextos de soporte

9. **Auth (identidad y acceso)** — esquema `auth`. User, RefreshToken, OneTimeToken. Versión 0.1.
10. **Settings (configuración)** — esquema `settings`. SettingsSection. Versión 0.1.
11. **Attachments (adjuntos)** — esquema `attachments`. Attachment, StorageProvider. Versión 0.3.
12. **Audit (auditoría)** — esquema `audit`. AuditEntry, AuditSignature. Transversal: escribe por hook de SQLAlchemy; expone consulta y verificación. Versión 0.1.
13. **Crypto (criptografía)** — esquema `crypto`. CryptoKey, CryptoOp, CryptoJob, KeyProvider. Transversal: todos los contextos con datos sensibles lo usan por el bus. Versión 0.1 (local), 0.2 (OpenBao), 0.3 (router admin).

### Contextos de lectura (sin tablas propias)

14. **Dashboard (inicio)** — módulo `dashboard`, sin esquema. Compone consultas de los services de memberships, payments, classes, notifications y wods. Versión 0.1, crece por versión.
15. **Portal (yo)** — módulo `portal`, sin esquema. Expone `/me/*` filtrando por el `member_id` del token y delegando en los services de members, memberships, payments, results, athletes y notifications. Versión 1.0.
16. **TV** — módulo `tv`, sin esquema. Lectura pública con token de dispositivo (de Settings) sobre wods y results. Versión 0.5.

## 2. Relaciones entre contextos

Notación: `A → B` significa que A depende de B. Patrón entre paréntesis.

### Núcleo comercial (v0.1)

- Memberships → Plans (**Conformist**): Memberships lee el plan por `plans.service.get(plan_id)` y copia precio y reglas de duración. Plans no sabe de Memberships, salvo la consulta `memberships.service.count_active_by_plan(plan_id)` que Plans invoca antes de permitir una baja (RN-08). Esa consulta es la única llamada en sentido contrario y está documentada.
- Memberships → Members (**Customer/Supplier**): Memberships valida que el socio exista y no esté dado de baja. Members pide a Memberships `membership_status_for(member_ids)` para la lista y los chips. Ambas llamadas pasan por `service.py`.
- Payments → Memberships (**Customer/Supplier** con **eventos**): Payments valida que la membresía exista y no esté cancelada; después emite `PaymentRegistered` y `PaymentVoided`. Memberships se suscribe y decide activación. Payments nunca cambia el estado de una membresía directamente.
- Memberships `sell` → Payments (**llamada de service en la misma transacción**): `sell` crea la membresía y llama a `payments.service.register(...)` si viene `first_payment`. Es la única dependencia de Memberships hacia Payments y existe para cumplir S5 sin romper la inmutabilidad del pago.

### Entrenamiento (v0.4 a v0.6)

- Classes → Members (**Conformist**): lee nombre y estado de membresía para el check-in (vía `memberships.service.status_for(member_id)`).
- Memberships ← Classes (**eventos**): `MemberCheckedIn` y `AttendanceRemoved` descuentan o devuelven clases.
- Training → Classes (**Conformist**): un resultado puede referir una sesión; un WOD se asigna a sesiones del día.
- Training → Members (**Conformist**): nombre y sexo para el leaderboard. Training nunca lee campos cifrados.
- Athletes ← Training (**eventos**): `WodResultValidated` deriva récords. Athletes lee el catálogo de movimientos por `wods.service`.

### Avisos (v0.2)

- Notifications ← Memberships (**eventos**): `MembershipExpiring`, `MembershipExpired`, `MembershipActivated`.
- Notifications → Members (**Customer/Supplier**): pide canales activos, suscripciones push y el teléfono o correo descifrado para enviar (vía `members.service.contact_for_notification(member_id)`, que audita el descifrado con propósito `notify`).
- Notifications → Settings (**Conformist**): credenciales y canales habilitados.

### Soporte

- Auth → Members (**Partnership** desde v1.0): un usuario `member` apunta a un socio; crear la cuenta de portal se dispara desde Members (`MemberCreated` o acción explícita) y Auth la crea. Auth no lee datos cifrados del socio: el correo de login se guarda en `auth.users.email` en claro por diseño (es credencial, no dato personal del padrón) — supuesto a confirmar en el gate (**P5**).
- Dashboard → todos los de negocio (**Conformist**, solo lectura por services).
- Portal → Members, Memberships, Payments, Training, Athletes, Notifications (**Conformist**, solo filtrado por `member_id`).
- TV → Training, Settings (**Conformist**).
- Attachments ← Members (**Customer/Supplier**): Members pide subir foto y consentimiento con `owner_table = members`.
- Audit ← todos (**Published Language** por hook): cualquier tabla con `__audited__ = True` escribe auditoría sin llamar a nada. Audit no depende de nadie.
- Crypto ← Members, Athletes, Attachments, Audit (firmas), Backup (**Shared Kernel** restringido): el bus es la única puerta (`encrypt`, `decrypt`, `blind_index`, `sign`, `verify`). Crypto no depende de ningún contexto de negocio.
- Settings ← Payments (medios), Classes (horas, cupo por defecto), Notifications (canales), TV (token), Members (versión de política de privacidad) (**Conformist**).

## 3. Diagrama

```
                 ┌──────────────┐      ┌──────────────┐
                 │   Settings   │      │    Audit     │◄── hook de toda tabla auditada
                 └──────┬───────┘      └──────────────┘
                        │ conformist
   ┌────────┐   C/S   ┌─┴──────────┐  eventos  ┌───────────┐
   │ Plans  │◄────────┤ Memberships│◄──────────┤ Payments  │
   └────────┘         │   (sell)   ├──────────►│           │
                      └─┬───┬──────┘ llamada   └───────────┘
            status_for  │   │ eventos (expiring, expired, activated)
   ┌────────┐           │   ▼
   │Members │◄──────────┘ ┌──────────────┐  contacto   ┌─────────┐
   │(cifrado)│◄───────────┤Notifications │────────────►│ Members │
   └───┬────┘             └──────────────┘             └─────────┘
       │ conformist (nombre, sexo)           ▲ eventos
   ┌───┴────┐  eventos   ┌──────────┐   ┌────┴─────┐  eventos  ┌──────────┐
   │Classes ├───────────►│Memberships│   │ Training │──────────►│ Athletes │
   └────────┘ checkin    └──────────┘   │wods+res. │           └──────────┘
                                        └────┬─────┘
                                             │ lectura con token de dispositivo
                                        ┌────┴─────┐
                                        │    TV    │
                                        └──────────┘
   Lectura compuesta: Dashboard (admin/coach) y Portal (/me) → services de todos.
   Shared kernel restringido: core/crypto (bus) y core/security (JWT, argon2, roles).
```

## 4. Orden de construcción derivado del mapa

Las flechas de dependencia fijan el orden; coincide con las versiones del plan:

1. `core` (db, security, events, audit, crypto bus) y `auth`, `settings`.
2. `members`, `plans`.
3. `memberships`, `payments` (juntos, por `sell` y los eventos).
4. `dashboard` (v0.1 mínimo), `audit` router.
5. `notifications` (v0.2) y proveedor OpenBao.
6. `attachments`, router de `crypto`, firma de auditoría (v0.3).
7. `classes` (v0.4).
8. `wods`, `results`, `tv` (v0.5).
9. `athletes` (v0.6).
10. `portal` (v1.0).

## 5. Lo que queda explícitamente prohibido entre contextos

- Importar `models` de otro módulo o hacer `JOIN` entre esquemas fuera del `service.py` dueño.
- Encadenar tres services en un router: cuando una acción interesa a varios contextos se emite un evento.
  - Precisión aprobada en el gate (G-04): una **lectura** sí puede recorrer aristas que ya existen en este mapa hasta profundidad 2, con consultas por lote, sin escribir ni emitir eventos y llamando a un solo service desde el router. Ejemplo: `members.service.list` pide `memberships.service.status_for(member_ids)`, que devuelve `{status, plan_id, plan_name, end_date}` resolviendo los nombres con `plans.service.names_for`. La prohibición de tres services sigue intacta para escrituras.
  - Dependencias mutuas entre services (G-03): el sentido minoritario usa un puerto registrado al arrancar si solo valida, o un import perezoso si es lectura de presentación, solo para los pares de la lista blanca (v0.1: memberships ↔ payments, members ↔ memberships, plans ↔ memberships; v0.4: members ↔ classes). Lo vigila `tests/architecture/test_service_import_graph.py`.
- Que cualquier contexto distinto de Members, Athletes, Attachments y Audit llame al bus de cifrado para campos que no son suyos.
- Que Payments cambie el estado de una membresía, o que Memberships edite un pago.

## 6. Preguntas acumuladas para el gate

- **P5 (resuelta en el gate del 21 de octubre de 2026):** el correo de login del usuario de portal se guarda en claro en `auth.users.email` (es credencial), aunque `members.email` vaya cifrado. Alternativa descartada: índice ciego también en auth y login por documento.
- **P6:** ¿Un coach puede ser también socio (entrena en el box)? Supuesto: sí; un usuario `coach` puede tener `member_id` opcional, y el portal se le muestra con el rol de coach ampliado en v1.1 (fuera de alcance ahora).
