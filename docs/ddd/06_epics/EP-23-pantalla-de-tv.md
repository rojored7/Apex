# EP-23 · Pantalla de TV del box

- **Versión del plan:** v0.5 (versión 0.5 punto 2, "endpoint público de solo lectura para la pantalla de TV").
- **Bounded context:** TV (lectura, módulo `tv`, sin esquema), Conformist de Training y Settings.
- **Estimación relativa:** S.

## Objetivo de negocio

Reemplazar la pizarra de la pared por una TV que muestra el WOD del día y el leaderboard en vivo. Los atletas ven su marca al lado de la de los demás sin preguntarle al coach, y el box se siente más profesional.

## Actores

- Dispositivo TV: no es persona; usa un token de dispositivo de solo lectura.
- Administrador: genera y rota el token desde Configuración.

## Capacidades incluidas

### Backend
- `GET /tv/today` con token de dispositivo (de la sección `tv` de Settings), en la lista blanca de rutas sin rol de EP-03, pero protegido por el token.
- Respuesta solo con WOD del día y leaderboard: nombre, nivel y marca; ningún dato personal adicional ni cifrado.
- Token largo, rotable desde Configuración; al rotar, el anterior deja de funcionar de inmediato.

### Front
- Pantalla TV en `TvLayout` (1920 × 1080, solo tema oscuro, sin interacción), que se abre con `/tv?token=…` y refresca cada 30 segundos.
- Estado de "sin WOD publicado" y de "token inválido".

## Fuera de alcance

- Control remoto, rotación de pantallas o publicidad.
- Cronómetro de la clase.

## Criterios de éxito medibles

- Sin token o con un token rotado, `/tv/today` devuelve 401.
- La respuesta no contiene documento, teléfono, correo ni ningún campo cifrado (prueba de contrato).
- Un resultado registrado en la tablet aparece en la TV en menos de 30 segundos.
- La pantalla funciona 12 horas seguidas sin recargar manualmente ni fugas de memoria visibles.

## Dependencias

- EP-22 Entrenamiento (WOD y leaderboard).
- EP-05 Configuración del gimnasio (sección `tv` y regeneración del token).
- EP-03 Seguridad de la plataforma (lista blanca de rutas).
- EP-06 Layout y componentes compartidos del front (`TvLayout`).

## Riesgos

- Un token filtrado muestra nombres y marcas; riesgo aceptado porque es información que ya está en la pizarra (`04_architecture_decision.md` sección 8).
- La TV en la LAN sin TLS mientras no exista EP-20.

## Pantallas del diseño que habilita

- `TV`.
