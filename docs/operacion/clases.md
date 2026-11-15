# Clases, horario y check-in en la tablet

Guía para quien deja lista la tablet del box. Cubre el modo quiosco del check-in (S7-D24, S7-D41).

## Cuenta propia del dispositivo

- Crea una cuenta de **coach** solo para la tablet (por ejemplo `tablet@tubox.co`). Nunca uses una cuenta de administrador.
- La cuenta del coach puede buscar socios (nombre, estado de la membresía y foto), registrar llegadas y quitar las de hoy o de ayer. No puede ver documento, teléfono ni correo del socio.
- Entra una vez con esa cuenta, abre una sesión de clase en **Clases** y toca **Abrir check-in**.

## Modo quiosco (tablet del check-in)

El confinamiento lo impone el servidor (decisión S7-D41), no solo la pantalla:

- Al abrir el check-in de una sesión, el front llama `POST /auth/kiosk` con
  `{"path": "/clases/<id>/checkin"}`. La sesión de refresco queda marcada (`kiosk_path`) y el
  access nuevo lleva `kiosk: true`; el front lo pone en la sesión en lugar del anterior. La marca
  sobrevive a la rotación del refresh (cada 15 min) y se borra al cerrar sesión.
- Con la marca, el servidor responde 403 `kiosk_mode` a toda ruta que no sea del check-in:
  nada de revelar teléfono, correo o documento, descargar adjuntos sensibles, exportar, ver
  pagos, usuarios o auditoría. Solo pasan: `GET /auth/me`, `POST /auth/kiosk`,
  `POST /auth/kiosk/exit`, `GET /class-sessions` (y por id), `GET`, `POST` y `DELETE
  /attendance`, `GET /members?q=` y `GET /attachments/{id}` (solo la foto).
- `GET /auth/me` trae `kiosk_path`: el front redirige a esa ruta al recargar, con «atrás» o al
  escribir otra dirección. Un 403 `kiosk_mode` en cualquier pantalla también vuelve al check-in.
- **Salir** pide la contraseña de la cuenta (`POST /auth/kiosk/exit`). No abre una sesión nueva ni
  rota el refresh, y una contraseña errada NO cuenta para el bloqueo de la cuenta. Tras 5 fallos
  en 15 minutos para ese usuario, el servidor responde 429 (espera el `Retry-After`). La respuesta
  trae un access sin la marca. «Vender» (socio sin plan) también la pide, porque lleva al panel.
- **Cambiar de clase sin salir** (S7-D42): arriba del check-in aparece el selector «Clases de hoy» con las sesiones programadas de hoy. Elegir otra llama `POST /auth/kiosk` con la ruta nueva, sin contraseña; el servidor solo la acepta si es de hoy o de ayer (si no, 403 `kiosk_mode`).
- A los **10 minutos sin tocar la pantalla** la sesión se cierra (`POST /auth/logout`, la marca
  muere con ella) y la tablet vuelve al inicio de sesión.
- Un access emitido antes de entrar al quiosco puede vivir hasta 15 minutos sin la marca; el
  front lo reemplaza por el de la respuesta de `POST /auth/kiosk`.
- Abrir una ruta nueva al quiosco exige editar `KIOSK_ALLOWED_ROUTES` (`core/security.py`) y
  `tests/architecture/test_kiosk_routes.py`.
- Revisión de C4 (S7-C4b): la salida exige la sesión de la cookie con la marca antes de verificar
  la contraseña, y el tope de 5 fallos en 15 minutos es por usuario y sesión (una tablet no
  bloquea al coach en otra). Un admin en quiosco quita asistencias con la regla del coach (hoy o
  ayer). En quiosco, `GET /attendance` exige `session_id` y `GET /members` exige `q` (sin filtros
  de estado, plan, consentimiento ni última asistencia). Cerrar sesión con la marca queda
  auditado (`KioskExited`, `via = logout`).
- Cambiar de clase dentro del quiosco (S7-D42): con la marca puesta, `POST /auth/kiosk` solo
  acepta el check-in de una clase de hoy o de ayer; otra da 403 `kiosk_mode`.
- Aceptado: el tope de la salida vive en la memoria del proceso (varios workers lo multiplican,
  como el del login); la tablet no queda atada a una sola clase; el quiosco ve la foto de
  cualquier socio.
- Lista de socios: `GET /members?last_attendance=7d|14d|30d|60d|never` filtra por última
  asistencia (corte `hoy - N` en Bogotá; `never` = nunca asistió) y cada fila trae
  `last_attendance_at` y `membership_classes_remaining`.

## Instalación recomendada

- Navegador en **modo quiosco** o con acceso guiado (Android: fijar pantalla; iPad: Acceso guiado; Chrome: `--kiosk`), con la página del check-in como inicio.
- **Sin gestor de contraseñas** ni autocompletado del navegador: la contraseña no debe quedar guardada en la tablet.
- Bloqueo de pantalla del sistema activo.

## Límites que conviene conocer

- El token de dispositivo (una credencial propia de la tablet que no inicia sesión de persona) queda para v0.5.
- Vencida o sin plan, la persona entra igual y queda marcada; el coach la ve en rojo con texto. Nunca se bloquea la puerta desde la app.
- Una sesión de otra fecha registra con la advertencia «Otro día»; no es un error.
