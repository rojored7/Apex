# Clases, horario y check-in: operación

## Modo quiosco (tablet del check-in)

La tablet del gimnasio usa la cuenta de un coach. Para que un socio no pueda salir del check-in
con «atrás», la barra de direcciones o una recarga, el confinamiento lo impone el servidor
(decisión S7-D41):

- Al abrir el check-in de una sesión, el front llama `POST /auth/kiosk` con
  `{"path": "/clases/<id>/checkin"}`. La sesión de refresco queda marcada (`kiosk_path`) y el
  access nuevo lleva `kiosk: true`. La marca sobrevive a la rotación del refresh (cada 15 min) y
  se borra al cerrar sesión.
- Con la marca, el servidor responde 403 `kiosk_mode` a toda ruta que no sea del check-in:
  nada de revelar teléfono, correo o documento, descargar adjuntos sensibles, exportar, ver
  pagos, usuarios o auditoría. Solo pasan: `GET /auth/me`, `POST /auth/kiosk`,
  `POST /auth/kiosk/exit`, `GET /class-sessions` (y por id), `GET`, `POST` y `DELETE
  /attendance`, `GET /members?q=` y `GET /attachments/{id}` (solo la foto).
- `GET /auth/me` trae `kiosk_path`: el front redirige a esa ruta al recargar.
- Salir: `POST /auth/kiosk/exit` con la contraseña del coach. No abre una sesión nueva ni rota el
  refresh, y una contraseña errada NO cuenta para el bloqueo de la cuenta. Tras 5 fallos en 15
  minutos para ese usuario, el servidor responde 429 (espera el `Retry-After`). La respuesta trae
  un access sin la marca.
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
  acepta el check-in de una clase programada de hoy o de ayer; otra (o una cancelada) da 403
  `kiosk_mode`. En quiosco `GET /attendance?session_id=` solo ve clases de hoy o de ayer y
  `GET /members` pide `q` de al menos 3 letras, sin orden y con páginas de hasta 20.
- `GET /members/export` acepta `last_attendance` igual que la lista.
- Aceptado: el tope de la salida vive en la memoria del proceso (varios workers lo multiplican,
  como el del login); la tablet no queda atada a una sola clase; el quiosco ve la foto de
  cualquier socio.
- Lista de socios: `GET /members?last_attendance=7d|14d|30d|60d|never` filtra por última
  asistencia (corte `hoy - N` en Bogotá; `never` = nunca asistió) y cada fila trae
  `last_attendance_at` y `membership_classes_remaining`.
