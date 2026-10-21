# EP-24 · Perfil del atleta

- **Versión del plan:** v0.6 (versión 0.6 completa).
- **Bounded context:** Athletes (negocio, esquema `athletes`).
- **Estimación relativa:** L.

## Objetivo de negocio

Que cada atleta tenga su historia: sus récords personales, sus mejores tiempos en benchmarks y la evolución de su peso y medidas. El coach puede mostrarle al socio que está progresando, que es la razón principal para que renueve.

## Actores

- Administrador y coach: registran medidas y récords manuales, consultan el perfil.
- Training: emite los resultados validados que derivan récords.
- Socio: consumidor futuro desde el portal (EP-25).

## Capacidades incluidas

### Backend
- Entidad `BodyMetric`: fecha de medición, peso y medidas cifradas con la clase `athlete.metric`, notas, quién registró (RN-13).
- Entidad `PersonalRecord`: `kind` (`rm` con `movement_id` o `benchmark` con `wod_id`), valor, fecha, `source` (`manual` o `derived`), `result_id` si es derivado; nunca se borra.
- Función pura `athletes.derive_record(result, current_rm)`.
- RN-12: suscripción a `WodResultValidated`; un resultado validado con `load_kg` mayor al RM vigente del movimiento crea un récord derivado.
- Comparación de benchmarks: historial de un socio en un mismo WOD benchmark.
- Lectura del catálogo de movimientos por `wods.service`.
- Mostrar en claro una medida pasa por el bus y se audita (`SensitiveFieldRevealed`).
- Evento `PersonalRecordSet`.
- Endpoints (un RM es un récord con `kind = rm`, `BRECHAS.md` sección 3): `GET /athletes/{id}/metrics`, `POST /athletes/{id}/metrics`, `GET /athletes/{id}/records?kind=`, `POST /athletes/{id}/records` (manual), `GET /athletes/{id}/benchmarks?wod=`.

### Front
- Perfil del atleta como pestaña de la ficha, con subpestañas Resumen, Medidas, RMs, Récords y Benchmarks.

## Fuera de alcance

- Envío de push al socio por un récord nuevo (no hay regla de aviso que lo defina; ver preguntas abiertas).
- Registro de peso por el propio socio (EP-25).
- Planes de nutrición o entrenamiento personalizados.

## Criterios de éxito medibles

- Un resultado validado de 100 kg sobre un RM vigente de 95 kg crea un récord derivado; uno de 90 kg no crea nada.
- Las medidas no aparecen en claro en la base.
- Cada vez que una medida se muestra en claro queda una fila de auditoría.
- Un récord manual y uno derivado del mismo movimiento conviven y el vigente es el de mayor valor.
- La comparación de benchmarks muestra todos los intentos del socio en orden cronológico.

## Dependencias

- EP-22 Entrenamiento (resultados validados, catálogo de movimientos, WODs benchmark).
- EP-02 Bus de criptografía (`athlete.metric`).
- EP-07 Padrón de socios (ficha).
- EP-06 Layout y componentes compartidos del front.

## Riesgos

- RN-12 habla del "movimiento principal" del WOD, pero el modelo no define cuál es en un WOD con varios movimientos (ver preguntas abiertas).
- No está definido si se cifran todas las medidas o solo el peso (el modelo y el catálogo de clases de dato difieren).
- No hay regla para derivar récords de benchmarks (solo de carga).

## Pantallas del diseño que habilita

- `Atleta_Perfil`, pestaña Atleta de `Socio_Ficha`.
