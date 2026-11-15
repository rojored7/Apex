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
