# EP-16 · Recibos y exportaciones — desglose técnico de épica

- **Épica:** `docs/ddd/06_epics/EP-16-recibos-y-exportaciones.md`
- **Versión:** v0.2
- **Historias:** US-137 a US-139 (3 historias, 13 puntos)

## Resumen

- Tres salidas de datos, todas de solo lectura y todas auditadas:
  - el recibo en PDF de un pago (US-137), con `reportlab` (BSD), para admin y coach, auditado como `download`;
  - la exportación de socios a CSV (US-138), solo para admin, que descifra por el bus en lotes y se audita como `export` con el filtro y el número de filas;
  - la exportación de pagos a CSV (US-139), solo para admin, auditada como `export`.
- Los dos CSV comparten el formato de N-29: separador `;`, BOM UTF-8, columnas exactas y escape de fórmulas.
- No hay migraciones: la acción `download` ya existe en el CHECK de `audit.audit_log` (`0002_audit_log`).

## Correcciones aplicadas por DECISIONES.md

- US-137 (contexto de dominio, alcance, criterio 5, BDD y supuesto) audita la descarga del recibo como `export`. Se audita como `download`, con tabla `payments`, el `record_id` del pago y el usuario, y `export` queda solo para listas: corregido por DECISIONES N-08.
- US-138 define las columnas `documento;nombres;apellidos;telefono;correo;fecha_nacimiento;sexo;contacto_emergencia_nombre;contacto_emergencia_telefono;estado;estado_membresia;creado`. Las columnas son exactamente `nombres;apellidos;documento;telefono;correo;estado_membresia;plan;vence;creado`, en ese orden, con `;` y BOM UTF-8:
  - solo se descifran `member.document`, `member.phone` y `member.email`;
  - nunca `member.birth_date` ni `member.emergency_contact`;
  - `plan` y `vence` son los de la membresía que define `estado_membresia`.
  
  Corregido por DECISIONES N-29.
- US-139 define las columnas `fecha_pago;socio;plan;medio;referencia;monto_cop;anulado;motivo_anulacion;registrado_por`. Las columnas son exactamente `fecha;socio;plan;monto;medio;referencia;registrado_por;anulado;motivo_anulacion`, en ese orden:
  - `fecha` en hora de Bogotá con formato `AAAA-MM-DD HH:MM`;
  - `monto` entero sin separadores;
  - `anulado` con `si` o `no`.
  
  Corregido por DECISIONES N-29.
- La exportación de pagos entra en v0.2, aunque la épica la deje fuera de alcance. Es CSV, solo para admin y auditada con el filtro usado: corregido por DECISIONES Q15.
- Para el recibo, el actor `by` siempre es el usuario del request. Si algún día lo genera el worker (no en v0.2), usa `SYSTEM_USER_ID`: anotado según DECISIONES N-15.
- Con OpenBao sellado, `GET /members/export` responde 503 `crypto_unavailable`. El recibo y la exportación de pagos no usan el bus y siguen funcionando: aplicado según DECISIONES N-16.
- Con N-01, las listas nunca muestran datos cifrados. La exportación no es una lista en pantalla: es una salida explícita, solo para admin, con confirmación y auditada como `export`. Es la salida que ya prevén `05_service_design.md` y S9. Sin cambio, coherente con DECISIONES N-01.

## Validación contra el dominio y la arquitectura

Dominio:
- Payment se lee y nunca se escribe. El trigger de inmutabilidad de `0011_payments_immutability` queda intacto, y el recibo de un pago anulado muestra `ANULADO`, `void_reason` y `voided_at` (RN-02).
- Dinero en `int` COP. Se muestra como `$ 120.000` en el PDF y sin separador en el CSV (RN-01).
- Funciones puras:
  - `payments.receipt_context(payment, membership_label, member_name, gym, method_labels, tz) -> ReceiptContext`;
  - `payments.format_cop(amount) -> "$ 120.000"`;
  - `payments.format_bogota(dt) -> "20 oct 2026, 6:30 p. m."`;
  - `payments.csv_row(payment, member_name, plan_name, registered_by_name, method_labels, tz) -> list[str]`;
  - `members.csv_row(member_plain, membership_label) -> list[str]`;
  - `core.export.escape_formula(value) -> str` (antepone `'` a `=`, `+`, `-` y `@`).

Dependencias entre módulos. Ningún módulo importa `models` ajenos:
- El recibo (`payments.service`) lee el pago propio y pide:
  - `memberships.service.labels_for([membership_id])` → `plan_name`, `start_date`, `end_date`, `member_id`;
  - `members.service.names_for([member_id])`, solo nombre y apellido en claro;
  - `settings.service.get_section("gym")` y `settings.service.payment_methods()`.
- La exportación de pagos pide `memberships.service.labels_for(ids)`, `members.service.names_for(ids)` y `auth.service.names_for(user_ids)`, este último para `registrado_por` (contrato de US-110).
- La exportación de socios pide `memberships.service.current_for(member_ids)` → `status`, `plan_name`, `end_date`, y filtra con `memberships.service.member_ids_by_status` (US-092).
- Todas son consultas de solo lectura, por lote y de un solo nivel desde el service dueño. Las escrituras son solo la fila de auditoría y `crypto_ops`. Es el patrón de US-091 y US-098, así que no cuenta como encadenar services en una escritura.
- `labels_for` y `current_for` resuelven el nombre del plan dentro de `memberships.service`, con `plans.service.names_for`, porque Memberships → Plans es la relación Conformist documentada. Payments y Members no hablan con Plans.

Criptografía:
- Solo `members.service` descifra campos de socios (mapa de contextos, sección 5). Usa el contexto de lote de US-029 (`with bus.batch("decrypt", data_class)`), con un `batch_id` por lote de 500 y una fila de `crypto_ops` por lote y clase.
- Payments no toca el bus: el recibo y su CSV no llevan documento, teléfono ni correo.
- Lint `banned-api`: `reportlab` y `csv` no son primitivas prohibidas. El SHA-256 de cualquier verificación no se usa aquí.

Auditoría:
- Se escribe explícitamente con `core.audit.record(...)` en la misma transacción, como hace `reveal` en US-074:
  - recibo: `action = "download"`, `table_name = "payments"`, `record_id = payment_id`;
  - exportación de socios: `action = "export"`, `table_name = "members"`, `record_id = null`, `after = {filters, rows}`;
  - exportación de pagos: `action = "export"`, `table_name = "payments"`, `after = {filters, rows}`.
- El número de filas se calcula antes de transmitir: se seleccionan primero los ids que cumplen el filtro, se audita y después se descifra por lotes mientras sale el stream.

Roles:
- Recibo: admin y coach. El rol `member` recibe 403 (lo tendrá en `/me`, EP-25), sin sesión 401 y un id inexistente 404. Es coherente con la épica y con US-137.
- Las dos exportaciones son solo para admin: el coach recibe 403 antes de descifrar o consultar nada.

Rutas, paginación y fechas:
- `/members/export` y `/payments/export` se registran antes de `/members/{id}` y `/payments/{id}`.
- Las exportaciones no paginan, porque son una salida completa del filtro. Llevan los mismos filtros validados de la lista, con 422 y `field` si un filtro viene mal.
- Fechas en UTC en la base, y en hora de Bogotá en el PDF y el CSV, porque son documentos para personas y no la API JSON.

## Tablas y migraciones

- No aplica. No hay tablas nuevas.
- `download` ya está en el CHECK de `audit.audit_log.action` desde `0002_audit_log` (N-08). Si esa migración ya se aplicó sin ese valor, se agrega `0035_audit_action_download` (CHECK ampliado, con downgrade), dentro del rango 0035-0039.

## Services y eventos

`payments.service`:
- `receipt_pdf(id, by) -> bytes`: consultas por lote, `receipt_context`, `payments/receipt.py` y auditoría `download`.
- `export(filters, by) -> Iterator[bytes]`: los mismos filtros de `list`, ordenados por `paid_at`, con una consulta por lote de nombres y auditoría `export`.
- `payments/receipt.py`:
  - `render_receipt(ctx) -> bytes` con `reportlab.platypus`;
  - logo `apex-logo-light-bg.png` empaquetado en `api/src/app/modules/payments/assets/`;
  - datos de `settings.gym` (nombre, NIT, dirección, ciudad, teléfono, según N-18);
  - el texto fijo "Comprobante interno de pago. No es factura electrónica.";
  - sin documento, teléfono ni correo del socio.

`members.service`:
- `export(filters, by) -> Iterator[bytes]`, con los mismos filtros de `list` (`q`, `status`, `membership_status`, `plan_id`):
  - sin filtro, solo socios no dados de baja; con el filtro "Dados de baja", solo los que tienen `deleted_at` (RN-14);
  - descifra `document`, `phone` y `email` en lotes de 500;
  - auditoría `export`.

`core/export.py`, una utilidad compartida que no depende de ningún módulo:
- `csv_stream(header, rows) -> Iterator[bytes]`, con BOM UTF-8, `;`, comillas mínimas, saltos `\r\n` y `escape_formula` aplicado a cada celda;
- el escape de fórmulas también se aplica a los pagos (nombre y referencia), por seguridad y sin cambiar las columnas.

Contratos nuevos que esta épica le pide a EP-09:
- `memberships.service.labels_for(membership_ids) -> dict[id, MembershipLabel(member_id, plan_name, start_date, end_date)]`;
- `memberships.service.current_for(member_ids) -> dict[member_id, CurrentMembership(status, plan_name, end_date)]`. La membresía elegida es la misma que define `membership_status`: la última no cancelada, según el dominio 2.1 y N-26.

Otros contratos que se reutilizan:
- `members.service.names_for` (US-069 y US-070);
- `auth.service.names_for` (US-110);
- `memberships.service.member_ids_by_status` (US-092);
- `settings.service.payment_methods` (US-054).

Eventos: ninguno emitido ni consumido. Las salidas se auditan, no se modelan como evento de dominio.

## Endpoints

- `GET /api/v1/payments/{id}/receipt.pdf` — roles: admin, coach
- `GET /api/v1/members/export` — roles: admin
- `GET /api/v1/payments/export` — roles: admin

Formato de las respuestas:
- El recibo sale como `application/pdf` con `Content-Disposition: attachment; filename="recibo-<8 primeros del id>.pdf"`.
- Los CSV salen como `StreamingResponse` `text/csv; charset=utf-8` con `Content-Disposition: attachment; filename="socios-AAAAMMDD.csv"` o `"pagos-AAAAMMDD.csv"`.
- Todo con `Cache-Control: no-store`. El CSV no se escribe en disco ni en los logs.

## Componentes de front

Front condicionado a D1:
- `web/src/features/payments/components/ReceiptButton.tsx`:
  - va en el modal de detalle de `Pagos` y en cada fila de la pestaña Pagos de `Socio_Ficha`;
  - descarga por `fetch` con el token y un `Blob`, con estados de carga y error.
- `web/src/features/members/components/ExportButton.tsx`:
  - va en la barra de acciones de `Socios_Lista` y solo se muestra a admin (`useCan`);
  - pide confirmación con `ConfirmModal`: "La descarga contiene datos personales y queda registrada en la auditoría";
  - envía los filtros activos de la URL.
- `web/src/features/payments/components/ExportButton.tsx`: va en `Pagos`, con el mismo patrón y la confirmación obligatoria. Si el diseño no muestra el botón, se anota `// DESIGN-GAP:`.
- Lo compartido va en `web/src/shared/ui/`: `downloadBlob(response, fallbackName)`, que no depende de ninguna feature.
- Pruebas Vitest: visibilidad por rol, confirmación antes de descargar y manejo de 403 y 503. Todo con tokens, sin colores literales.

## Worker, CLI e infraestructura

- Dependencias del api:
  - `reportlab` (BSD), en `pyproject.toml` y `NOTICE`;
  - `pypdf` (BSD), solo en desarrollo, para extraer el texto del PDF en las pruebas.
- El chequeo de licencias de CI (`pip-licenses`) acepta `reportlab` y falla con `fpdf2` (LGPL), con un caso de prueba en el script de licencias.
- La imagen del api incluye `modules/payments/assets/apex-logo-light-bg.png`, copiado de `web/public/brand/`.
- No hay jobs ni comandos de CLI nuevos.
- Pruebas:
  - `api/tests/payments/test_receipt_pure.py`: cruce de medianoche UTC/Bogotá, pago anulado y pago sin referencia;
  - `api/tests/payments/test_receipt_service.py`: texto extraído del PDF, ausencia del documento y auditoría `download`;
  - `api/tests/payments/test_export.py`: cuadre con `summary(month)`, anulados y 422 en `from`;
  - `api/tests/members/test_export.py`: filtros, dados de baja, lotes con `count = 500`, auditoría, columnas de N-29, escape de fórmulas y 1.000 socios en menos de 10 s;
  - tests de router por rol (403 al coach sin ninguna fila nueva en `crypto_ops`);
  - tests de arquitectura que siguen en verde: `test_no_cross_models.py`, `test_every_route_has_role.py` y `test_banned_imports.py`.

## Dependencias

- De v0.1:
  - US-095 y US-096 (pagos y trigger), US-098 (filtros de la lista de pagos) y US-099 (modal de detalle);
  - US-100 (`summary(month)` para el cuadre);
  - US-069 y US-070 (socios y filtros) y US-071 y US-092 (`membership_status` y `member_ids_by_status`);
  - US-091 (`memberships.service`, base de `labels_for` y `current_for`);
  - US-054 y US-055 (secciones `gym` y `payment_methods`);
  - US-110 (`auth.service.names_for`);
  - US-015 y US-016 (auditoría, con `download` en el CHECK) y US-102 (las acciones se ven en la auditoría);
  - US-029 (lotes en `crypto_ops`);
  - US-034 (`require_role`);
  - US-009 (chequeo de licencias).
- De v0.2: US-136 (EP-15), para el 503 `crypto_unavailable` en la exportación de socios con OpenBao sellado.
- La consume EP-25 (`Portal_Pagos`), que reutiliza `receipt_pdf` filtrando por el `member_id` del token.

## Riesgos

- Front condicionado a D1: si el gate no aprueba S1, sale el front de las tres historias (unas 9 h).
- Una exportación CSV con datos en claro sale del sistema y queda fuera de cualquier control; la auditoría solo prueba que salió — mitigación: solo admin, confirmación explícita, auditoría con filtro y número de filas, `no-store`, y solo las columnas de N-29 (sin fecha de nacimiento ni contacto de emergencia).
- El recibo se puede confundir con una factura — mitigación: el texto fijo "Comprobante interno de pago. No es factura electrónica." y ninguna numeración consecutiva propia (se usa el id del pago).
- Auditoría escrita antes de terminar el stream: si la descarga se corta, queda registrada una exportación incompleta — mitigación: se acepta, porque la auditoría prueba la intención y los datos que se seleccionaron. Así se documenta en `docs/operacion/`.
- Rendimiento de 1.000 socios en menos de 10 s — mitigación: descifrado en lotes de 500 con las DEK en memoria, consultas por lote a memberships y una prueba de rendimiento en CI.
- Inyección de fórmulas en hojas de cálculo — mitigación: `escape_formula` en `core/export.py` aplicado a todas las celdas de los dos CSV, con prueba.
- Fan-out de lectura: el recibo consulta cuatro módulos. Si el gate interpreta la regla de "no encadenar tres services" también para lecturas fuera de `dashboard` y `portal`, US-137 y US-139 tendrían que pasar por un contexto de lectura — mitigación: se sigue el patrón ya aceptado en US-091 y US-098, y se anota para el gate.

## Estado y estimación por historia

- US-137 · Descargar recibo de pago — **READY** — 23 h — PDF con `reportlab` y `receipt_context` puro, sin datos cifrados, con marca de anulado; roles admin y coach (el socio, en EP-25); auditado como `download` (corregido por N-08); necesita `memberships.service.labels_for`.
- US-138 · Exportar socios a CSV — **READY** — 19 h — CSV con las columnas exactas de N-29 (solo descifra documento, teléfono y correo, en lotes de 500), `;` y BOM, escape de fórmulas, streaming, solo admin y auditado `export` con filtro y filas; necesita `memberships.service.current_for`.
- US-139 · Exportar pagos a CSV — **READY** — 12 h — CSV con las columnas exactas de N-29 (Q15) que cuadra con `summary(month)` y marca los anulados, sin campos cifrados, solo admin y auditado `export`; usa `core/export.py`, compartido con US-138.

## Total de la épica

- **Total: 54 h**
