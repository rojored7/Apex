# 01 · Descubrimiento de producto

Fecha: 21 de octubre de 2026.
Fuentes: `CLAUDE.md`, `docs/PLAN.md`, `docs/design/*`, `docs/BRECHAS.md`. Donde las fuentes callan, se declara un supuesto y se acumula para el gate humano único.

## 1. Visión

APEX es el sistema de administración de un gimnasio de CrossFit en Colombia, de un solo local. Reemplaza el cuaderno, el Excel y los chats de WhatsApp con los que hoy se controla quién está al día, quién vence, quién pagó y cómo entrenó cada socio. Corre en un servidor propio del gimnasio (Docker en Linux), se usa desde el computador de recepción, una tablet en el piso del box, una TV en la pared y el celular del socio.

Frase guía: **"Que el dueño sepa en 10 segundos quién está al día, quién vence esta semana y a quién hay que avisarle; y que el socio vea su plan, sus pagos y sus marcas sin preguntar."**

## 2. Problema que resuelve

- El control de membresías es manual y se pierden vencimientos: socios entrenando vencidos y plata que no entra.
- Los pagos (efectivo, Nequi, Bre-B) se anotan a mano y no se pueden auditar; cuando hay un error no queda rastro.
- Los avisos de vencimiento se mandan uno a uno por WhatsApp, cuando alguien se acuerda.
- Los resultados de los WODs viven en una pizarra que se borra cada día; el atleta no tiene historial ni récords.
- Los datos personales (cédula, teléfono, correo, fecha de nacimiento, contacto de emergencia) están en archivos sin cifrar, con riesgo legal bajo la Ley 1581 de 2012 de protección de datos.

## 3. Actores

- **Administrador (admin):** dueño o recepcionista principal. Todo: socios, planes, membresías, pagos, anulaciones, usuarios, auditoría, llaves, configuración.
- **Coach:** entrenador. Ve y usa inicio, socios (ver, crear, editar), vender membresías y registrar pagos (sin anular), clases, check-in, WODs, movimientos, resultados, atleta, avisos. No ve planes ni sistema.
- **Socio (member):** atleta con cuenta en el portal. Solo lo suyo: plan, pagos, WODs, récords, datos, avisos. Puede enviar un resultado que queda pendiente de validación.
- **Dispositivo TV:** no es persona; una pantalla con token de dispositivo que lee el WOD y el leaderboard del día.
- **Worker:** proceso interno programado que recalcula vencimientos, genera avisos, firma la auditoría y verifica backups.

## 4. Capacidades del producto (alcance completo, v1.0)

Numeración tomada del índice de pantallas del diseño.

1. **Socios:** alta, edición, baja lógica, búsqueda por nombre, documento o teléfono sin descifrar la tabla, ficha con pestañas (membresías, pagos, asistencia, resultados, atleta, avisos, adjuntos, historial), foto y autorización de datos, exportación.
2. **Planes:** catálogo con precio en COP, tipo por días o por clases, activar y desactivar; no se borra un plan con membresías activas.
3. **Membresías:** vender, renovar, congelar (extiende la fecha de fin), anular con motivo; estados al día, por vencer, vencido, congelado, cancelado; resumen de conteos.
4. **Pagos:** registrar (efectivo, Nequi, Bre-B), anular con motivo y crear uno nuevo, nunca editar ni borrar; una membresía se activa cuando los pagos cubren el precio pactado; reporte mensual por medio; recibo en PDF.
5. **Clases y check-in:** horario semanal configurable, sesiones generadas, cupo, coach asignado, check-in en tablet que nunca bloquea (un vencido entra marcado en rojo), reportes de asistencia.
6. **Movimientos:** catálogo de movimientos con categoría.
7. **WODs:** calendario de WODs, movimientos con reps y cargas RX, benchmarks.
8. **Resultados:** registro por sesión en tablet (tiempo, rondas, reps, carga), nivel RX, RX+ o escalado, leaderboard del día por nivel y sexo, validación de los enviados por socios.
9. **Atleta:** medidas corporales cifradas, récords personales manuales y derivados (un resultado con carga superior crea el récord), comparación de benchmarks.
10. **Avisos:** reglas (3 días antes, el día, 1, 7 y 15 días después), plantillas, canales web push, correo, Telegram y enlace de WhatsApp; pantalla "por avisar hoy" para enviar a mano; historial de envíos.
11. **Usuarios y roles:** cuentas admin, coach y socio; bloquear, reenviar enlace de activación, cerrar sesiones.
12. **Auditoría:** cada cambio en tablas auditadas queda en una cadena de hashes; verificación de integridad; firma nocturna con ML-DSA (v0.3).
13. **Llaves de cifrado:** inventario de llaves por clase de dato, bitácora de operaciones, rotación por lotes con progreso, informe CBOM.
14. **Configuración:** datos del gimnasio, horas, medios de pago, canales, clases, membresías, token de TV, privacidad.
15. **Inicio:** tablero con socios al día, por vencer, vencidos, ingresos del mes, asistencia de la semana, sesiones de hoy, por avisar, últimos movimientos.
16. **TV:** WOD del día y leaderboard, 1920 por 1080, sin interacción, se abre con token.
17. **Portal del socio:** inicio, pagos con recibo, WODs y envío de resultado, progreso (récords, RMs, benchmarks, peso), datos propios y cambio de contraseña, avisos y canales.

## 5. Reglas de negocio con nombre (las que gobiernan el dominio)

- **RN-01 Dinero entero:** todo monto es un entero en pesos colombianos; no hay decimales.
- **RN-02 Pago inmutable:** un pago nunca se modifica ni se borra; se anula con motivo y se registra otro.
- **RN-03 Activación por cobertura:** una membresía pasa a activa cuando la suma de pagos no anulados es mayor o igual al precio pactado.
- **RN-04 Precio pactado:** la membresía copia el precio del plan en el momento de la venta; cambiar el plan después no cambia membresías vendidas.
- **RN-05 Fecha de fin:** plan por días: fin = inicio + duración; plan por clases: fin = inicio + duración máxima y además se descuentan clases por asistencia.
- **RN-06 Estados por fecha:** al día si hoy ≤ fin; por vencer si faltan 7 días o menos; vencido si hoy > fin; congelado entre `frozen_from` y `frozen_to`; cancelado es terminal.
- **RN-07 Congelar extiende:** congelar N días corre la fecha de fin N días.
- **RN-08 Plan con membresías activas no se borra:** solo se desactiva.
- **RN-09 Check-in nunca bloquea:** un socio vencido o sin plan entra y queda marcado.
- **RN-10 Una asistencia por sesión y socio.**
- **RN-11 Un resultado por WOD y socio;** el enviado por el socio nace `pending` hasta que un coach lo valide.
- **RN-12 Récord derivado:** un resultado validado con `load_kg` superior al récord vigente de ese movimiento crea un récord nuevo.
- **RN-13 Datos sensibles cifrados:** documento, teléfono, correo, fecha de nacimiento, contacto de emergencia y medidas corporales van cifrados por clase de dato; búsqueda por índice ciego; mostrar en claro se audita.
- **RN-14 Borrado lógico:** socios, planes y usuarios se dan de baja con `deleted_at`; pagos, resultados, auditoría y llaves nunca se borran.
- **RN-15 Rol por endpoint:** nada sin rol salvo login, recuperación y health; coach no anula ni borra; socio solo lo suyo.
- **RN-16 Cadena de auditoría:** cada fila de auditoría lleva el hash de la anterior; una fila alterada rompe la cadena.
- **RN-17 Aviso idempotente:** una regla no genera dos avisos para la misma membresía y la misma fecha objetivo.

## 6. Restricciones no funcionales

- Un solo servidor Linux con Docker Compose; PostgreSQL 16; sin servicios en la nube obligatorios (backup cifrado se sube con rclone a donde el gimnasio decida).
- Uso concurrente bajo: menos de 10 usuarios de panel a la vez, hasta 1.000 socios, decenas de check-ins por hora. Las listas se paginan igual.
- Cifrado en reposo por campo con envelope (KEK en proveedor, DEK por clase de dato); OpenBao Transit desde v0.2; preparación post-cuántica (ML-DSA en firmas v0.3, ML-KEM en envoltura v1.0).
- JWT Ed25519 de 15 minutos, refresh de 7 días con revocación, argon2id, rate limit en login, CORS cerrado, CSP y cabeceras de seguridad en Nginx, TLS con Caddy desde v0.3.
- Licencias permisivas únicamente (ver `CLAUDE.md`); añadir ISC y OFL 1.1 a la lista por iconos y fuentes.
- Interfaz en español de Colombia, hora de Bogotá en pantalla, UTC en base.
- Accesibilidad: controles de 44 px (56 px en tablet), foco visible, contraste 4,5:1, el color nunca es el único portador de significado.
- Funciona con internet intermitente en el local: fuentes locales, nada crítico depende de un servicio externo salvo el envío de avisos.

## 7. Fuera de alcance (v1.0)

- Varias sedes o varios gimnasios en la misma instalación.
- Pasarela de pagos en línea; los pagos se registran, no se cobran.
- Facturación electrónica DIAN.
- App móvil nativa; el portal es web responsive (PWA opcional).
- Tienda, inventario, nómina de coaches.
- Chat o comunidad entre socios.

## 8. Supuestos tomados (se confirman en el gate único)

- **S1 (D1):** el front se construye en este repositorio, en `web/`, dentro de este flujo. El párrafo "Alcance" de `CLAUDE.md` se reescribe al aprobar.
- **S2 (D2):** el API pagina con `limit` y `offset` (máximo 200); el front traduce páginas a offset. `DESIGN.md` y `ROUTES.md` se corrigen.
- **S3 (D3):** carpeta del front `web/`; logos en `web/public/brand/`.
- **S4 (D4):** el front se construye en el orden de las versiones del backend (v0.1 primero); cada pantalla entra en el sprint en que existe su API.
- **S5 (D5):** vender membresía es una operación de dominio `sell` que crea la membresía y el primer pago en una transacción, expuesta como `POST /members/{id}/memberships` con `first_payment` opcional. Los pagos siguen siendo entidades inmutables y la activación sigue siendo por evento.
- **S6:** módulo `settings` entra en v0.1 (lo necesitan medios de pago, token de TV y canales).
- **S7:** `members.sex`, `auth.users.member_id` y `members.data_consent_at` entran desde v0.1 para evitar migraciones con datos.
- **S8:** medios de pago son un enum fijo en v0.1 (`cash`, `nequi`, `breb`).
- **S9:** recibo PDF con `reportlab` (BSD) en v0.2; exportación CSV solo admin y auditada en v0.2.
- **S10:** los seis módulos de entrenamiento (clases, movimientos, WODs, resultados, atleta) y el portal mantienen las versiones del plan (v0.4 a v1.0).

## 9. Preguntas abiertas para el gate

- **P1:** ¿Quién atiende recepción el día a día? Si es solo el dueño, la pantalla de usuarios puede esperar; si hay recepcionistas, el rol admin necesita diferenciarse de "dueño" en v1.1 (fuera de alcance ahora).
- **P2:** ¿Los planes por clases tienen vigencia máxima? Se asume que sí (por ejemplo, 12 clases en 60 días) y el formulario de planes pide ambos valores.
- **P3:** ¿El backup se sube a un destino externo desde el día uno? Se asume un bucket S3 compatible configurado por `.env`; si no hay, el backup queda local.
- **P4:** ¿Se quiere el recibo PDF en v0.1? Supuesto: v0.2.
