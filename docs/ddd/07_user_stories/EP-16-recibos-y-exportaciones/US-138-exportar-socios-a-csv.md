# US-138 · Como administrador quiero exportar la lista de socios a CSV para usarla en contabilidad o como respaldo propio, dejando rastro de la salida de datos

- **Épica:** EP-16 · Recibos y exportaciones
- **Bounded context:** Members (esquema `members`)
- **Versión:** v0.2
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Socios_Lista` (`/socios`, botón Exportar)

## Historia

Como administrador
quiero un botón "Exportar" en la lista de socios que descargue un CSV con los filtros aplicados
para sacar mi información del sistema sabiendo que la descarga queda auditada

## Contexto de dominio

- **Aggregate / entidades:** Member (con campos cifrados).
- **Reglas que aplica:** RN-13 (el descifrado masivo pasa por el bus y se audita), RN-14 (los dados de baja solo salen si el filtro los incluye), RN-15 (solo admin), S9 (exportación CSV solo admin y auditada en v0.2).
- **Eventos que emite:** ninguno de dominio; auditoría `export`.
- **Eventos que consume:** ninguno.
- **Funciones puras:** `members.csv_row(member_plain) -> list[str]` (orden de columnas fijo, escape de fórmulas).

## Alcance

- **Backend:** `members.service.export(filters, by)` que aplica los mismos filtros que `GET /members` (`q`, `status`, `membership_status`, `plan_id`), descifra por lotes de 500 con un `batch_id` en `crypto_ops`, y genera CSV UTF-8 con BOM, separador `;` y columnas `documento;nombres;apellidos;telefono;correo;fecha_nacimiento;sexo;contacto_emergencia_nombre;contacto_emergencia_telefono;estado;estado_membresia;creado`. Respuesta en streaming. Auditoría `export` con tabla `members`, filtros usados y número de filas. Endpoint `GET /api/v1/members/export`.
- **Front:** botón "Exportar" en `Socios_Lista` visible solo para admin (`useCan`), con `ConfirmModal` que advierte "La descarga contiene datos personales y queda registrada en la auditoría"; usa los filtros activos.

## Criterios de aceptación

1. `GET /api/v1/members/export` responde 200 con `text/csv` para admin y 403 para coach; sin sesión, 401.
2. El CSV respeta los filtros de la lista; sin filtros exporta los socios no dados de baja; con el filtro "Dados de baja" incluye solo los que tienen `deleted_at`.
3. Los campos cifrados salen en claro en el CSV, descifrados por el bus en lotes de 500, con un `batch_id` por lote en `crypto_ops`.
4. Cada exportación deja una fila de auditoría `export` con usuario, filtros y número de filas exportadas.
5. Los valores que empiezan por `=`, `+`, `-` o `@` se escapan con un apóstrofo para evitar inyección de fórmulas en hojas de cálculo.
6. Exportar 1.000 socios termina en menos de 10 s.
7. El CSV no se guarda en disco del servidor ni en logs; se transmite en streaming.
8. El botón no aparece para coach y la confirmación es obligatoria antes de descargar.

## Escenarios BDD

```gherkin
# language: es
Característica: Exportar socios a CSV

  Escenario: El administrador exporta los socios al día
    Dado 3 socios "Al día" y 2 "Vencidos"
    Y una sesión de administrador en la lista con el filtro "Al día"
    Cuando pulsa "Exportar" y confirma
    Entonces descarga un CSV con 3 filas de datos y la cabecera fija
    Y queda una entrada de auditoría "export" con el filtro "active" y 3 filas

  Escenario: Un coach no puede exportar
    Dado una sesión de coach
    Cuando llama a "GET /api/v1/members/export"
    Entonces recibe 403
    Y no se descifra ningún dato
```

## Endpoints

- `GET /api/v1/members/export` — rol(es): admin — entrada: `q`, `status`, `membership_status`, `plan_id` — salida: CSV en streaming — códigos: 200, 401, 403, 422.

## Pantalla

- `Socios_Lista` (`/socios`): botón "Exportar" en la barra de acciones y modal de confirmación.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `csv_row` con escape de fórmulas y contacto de emergencia vacío.
- **Pruebas:** service con base real (filtros, lotes, auditoría), router (roles), rendimiento con 1.000 socios, front (visibilidad por rol y confirmación).
- **Archivos principales:** `api/src/app/modules/members/service.py`, `api/src/app/modules/members/router.py`, `web/src/features/members/components/ExportButton.tsx`.

## Supuestos

- Supuesto: columnas, separador `;` y BOM UTF-8 (para que Excel en español lo abra bien) no están definidos en los documentos.
- Supuesto: la ruta `/members/export` se registra antes de `/members/{id}` para no chocar con el parámetro.

## Dependencias

- US-070 · Buscar y listar socios (filtros).
- US-029 · Bitácora `crypto_ops` por lote.
- US-102 · Consultar auditoría (la acción `export` es visible).

## INVEST

- **Independiente:** reutiliza filtros y bus.
- **Negociable:** columnas y formato.
- **Valiosa:** el dueño saca su información con control.
- **Estimable:** patrón de exportación conocido.
- **Pequeña:** un endpoint y un botón.
- **Testeable:** filas, auditoría y rol verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service, router y front en verde; cobertura de 80 % o más
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada
- [ ] Revisión de PR aprobada
