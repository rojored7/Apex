# Clases, horario y check-in en la tablet

Guía para quien deja lista la tablet del box. Cubre el modo tablet del check-in (S7-D24).

## Cuenta propia del dispositivo

- Crea una cuenta de **coach** solo para la tablet (por ejemplo `tablet@tubox.co`). Nunca uses una cuenta de administrador: el modo tablet limita la pantalla, no la cuenta.
- La cuenta del coach puede buscar socios (nombre, estado de la membresía y foto), registrar llegadas y quitar las de hoy o de ayer. No puede ver documento, teléfono ni correo del socio.
- Entra una vez con esa cuenta, abre una sesión de clase en **Clases** y toca **Abrir check-in**.

## Cómo funciona el modo tablet

1. Al abrir `/clases/<sesión>/checkin` la pestaña queda en modo tablet (se marca en memoria de la página).
2. En ese modo la pantalla no tiene enlaces al panel y nunca pide datos cifrados del socio (`/members/{id}`, `/reveal`); solo la foto.
3. **Salir** pide la contraseña de la cuenta. Sin ella la tablet sigue en el check-in. «Vender» (socio sin plan) también la pide, porque lleva al panel.
4. A los **10 minutos sin tocar la pantalla** la sesión se cierra (`POST /auth/logout`) y la tablet vuelve al inicio de sesión.

## Instalación recomendada

- Navegador en **modo quiosco** o con acceso guiado (Android: fijar pantalla; iPad: Acceso guiado; Chrome: `--kiosk`), con la página del check-in como inicio.
- **Sin gestor de contraseñas** ni autocompletado del navegador: la contraseña no debe quedar guardada en la tablet.
- Bloqueo de pantalla del sistema activo.

## Límites que conviene conocer

- El modo es un límite de pantalla, no una barrera de seguridad: recargar la página fuera del check-in o escribir otra dirección en un navegador sin quiosco sale del modo. Por eso la cuenta es de coach y por eso el quiosco.
- El token de dispositivo (una credencial propia de la tablet que no inicia sesión de persona) queda para v0.5.
- Vencida o sin plan, la persona entra igual y queda marcada; el coach la ve en rojo con texto. Nunca se bloquea la puerta desde la app.
- Una sesión de otra fecha registra con la advertencia «Otro día»; no es un error.
