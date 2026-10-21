# EP-22 · Entrenamiento: movimientos, WODs y resultados

- **Versión del plan:** v0.5 (versión 0.5, puntos 1 y 2, salvo el endpoint de TV, que va en EP-23).
- **Bounded context:** Training (negocio, esquemas `wods` y `results`; dos módulos en código que forman un solo contexto porque comparten lenguaje y cambian juntos).
- **Estimación relativa:** XL.

## Objetivo de negocio

Sacar los resultados de la pizarra que se borra cada día. El coach publica el WOD, registra las marcas en la tablet al terminar la clase y el box tiene un leaderboard del día por nivel y sexo. El atleta empieza a tener historial, que es lo que lo motiva a volver.

## Actores

- Administrador y coach: mantienen el catálogo de movimientos, programan WODs y registran resultados.
- Tablet del piso del box (sesión de coach).
- Athletes (EP-24): escucha los resultados validados.

## Capacidades incluidas

### Backend: movimientos y WODs (módulo `wods`)
- Aggregate `Movement`: nombre único, categoría (`weightlifting`, `gymnastics`, `monostructural`, `other`), unidad, activo; no se borra, se desactiva.
- Aggregate `Wod`: fecha, título, `score_type` (`time`, `rounds_reps`, `reps`, `load`), `time_cap_s`, `is_benchmark`, descripción.
- Entidad interna `WodMovement` con orden, reps y cargas RX por sexo, como copia de valores (cambiar el catálogo no cambia WODs pasados).
- Invariantes: un WOD principal por fecha, heredado por las sesiones del día, con la opción de asignar otro a una sesión concreta.
- Evento `WodPublished`.
- Endpoints: `/movements` (lista con filtros, crear, editar), `/wods` (por semana o por búsqueda y benchmark, crear y editar con sus movimientos), `GET /wods/{id}`, `GET /wods/today`.
- Asignación de WOD a `ClassSession.wod_id` (Training → Classes, Conformist).

### Backend: resultados (módulo `results`)
- Aggregate `WodResult`: WOD, socio, sesión opcional, `level` (`rx`, `rx_plus`, `scaled`), `seconds`, `rounds`, `reps`, `load_kg`, `scaled_notes`, `status`, quién registró y validó, `supersedes_id`.
- Value object `Score` con `results.validate_score(score_type, ...)`: `time` exige segundos, `rounds_reps` exige rondas y reps, `reps` exige reps, `load` exige carga.
- `results.leaderboard_order(score_type)`: tiempo ascendente, los demás descendente; `scaled` siempre después de `rx` y `rx_plus`.
- Invariantes: un resultado por WOD y socio (RN-11); nace `validated` cuando lo registra coach o admin; nunca se borra (RN-14), se corrige con un registro que reemplaza; trigger de inmutabilidad que solo permite las columnas de validación.
- Leaderboard del día por nivel y sexo, leyendo nombre y sexo de Members sin tocar campos cifrados.
- Eventos `WodResultRecorded` y `WodResultValidated`.
- Endpoints: `GET /wods/{id}/leaderboard?level&sex`, `GET /wods/{id}/results`, `GET /class-sessions/{id}/attendance` para la tablet, `PUT /results` (registrar o reemplazar).
- Campo "WOD de hoy" del tablero (EP-12).

### Front
- Catálogo de movimientos, calendario de WODs, formulario de WOD con sus movimientos y detalle de WOD con leaderboard filtrable.
- Registro de resultados en tablet a partir de la asistencia de la sesión.
- Pestaña Resultados de la ficha del socio y tarjeta "WOD de hoy" en Inicio.

## Fuera de alcance

- Resultados enviados por el socio y su validación (EP-25, v1.0).
- Récords personales derivados (EP-24).
- Pantalla de TV (EP-23).
- Programación automática de WODs o planes de entrenamiento.

## Criterios de éxito medibles

- Un resultado `time` sin segundos o un `load` sin carga devuelve 422.
- Un segundo resultado del mismo socio en el mismo WOD sin `supersedes_id` devuelve 409 (RN-11).
- El leaderboard ordena tiempo ascendente y pone `scaled` después de `rx` y `rx_plus` (prueba pura con casos de empate).
- Editar un movimiento del catálogo no cambia las cargas RX de un WOD pasado.
- Ninguna consulta del leaderboard lee columnas cifradas (prueba de arquitectura).
- Registrar los resultados de una clase de 15 socios en la tablet toma menos de 5 minutos (prueba de uso con el coach).

## Dependencias

- EP-21 Clases, horario y check-in (sesiones y asistencia).
- EP-07 Padrón de socios (nombre y sexo).
- EP-12 Tablero de inicio (campo WOD de hoy).
- EP-06 Layout y componentes compartidos del front.

## Riesgos

- La combinación de "uno por WOD y socio" con "se corrige con un registro que reemplaza" exige definir cómo convive la unicidad con `supersedes_id` (ver preguntas abiertas).
- El tamaño XL: si se necesita partir, el corte natural es movimientos y WODs primero, resultados después, dentro de la misma versión.
- Socios con `sex` nulo: hay que decidir en qué filtro del leaderboard aparecen.

## Pantallas del diseño que habilita

- `Movimientos`, `WOD_Lista`, `WOD_Form`, `WOD_Detalle`, `Resultados_Registro`, pestaña Resultados de `Socio_Ficha`, tarjeta WOD de hoy de `Inicio`.
