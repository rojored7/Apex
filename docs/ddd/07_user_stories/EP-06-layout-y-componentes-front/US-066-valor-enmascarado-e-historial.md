# US-066 · Como equipo quiero el valor enmascarado con botón mostrar y el panel de historial para que los datos sensibles nunca se vean sin una acción explícita y auditada

- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context:** presentación (`web/src/shared/ui/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Patrón `P_Ficha` (referencia; lo usan `Socio_Ficha` y `Atleta_Perfil`)

## Historia

Como equipo
quiero `MaskedValue` y `HistoryAside`
para que la ficha muestre documento, teléfono, correo y demás campos cifrados enmascarados hasta que alguien pulse "mostrar" (que llama al API y queda auditado), y para que el historial de cambios se lea al costado de la ficha

## Contexto de dominio

- **Aggregate / entidades:** consume `Member` (campos cifrados) y `AuditEntry` (historial).
- **Reglas que aplica:** RN-13 (mostrar en claro se audita); Q6 (reveal para admin y coach); la auditoría muestra blobs, nunca claro (EP-11).
- **Eventos que emite:** ninguno (el evento `SensitiveFieldRevealed` lo emite el backend en US-074)
- **Eventos que consume:** ninguno
- **Funciones puras:** `maskValue(kind, maskedFromApi) -> string`

## Alcance

- **Backend:** No aplica.
- **Front:** `MaskedValue` (muestra el valor enmascarado que llega del API, por ejemplo `•••• 0304`; botón "Mostrar" que ejecuta una función `onReveal()` provista por la feature; muestra el valor en claro solo en memoria del componente; botón "Ocultar"; vuelve a enmascarar al desmontar o tras 60 segundos; muestra "Sin dato" si el campo está vacío; oculta el botón si el usuario no tiene permiso según `useCan`); `HistoryAside` (lista cronológica de entradas con fecha en hora de Bogotá, usuario, acción y resumen de campos cambiados; carga incremental; los campos cifrados se muestran como "dato cifrado modificado").

## Criterios de aceptación

1. `MaskedValue` nunca recibe el valor en claro como prop inicial; solo el valor enmascarado del API y una función `onReveal`.
2. Pulsar "Mostrar" llama a `onReveal` exactamente una vez por pulsación; mientras espera, el botón muestra estado de carga.
3. El valor en claro no se guarda en caché de TanStack Query, en `localStorage` ni en la URL; se descarta al ocultar, al desmontar o a los 60 segundos.
4. Si `onReveal` falla con 403, el componente muestra "No tienes permiso para ver este dato" y sigue enmascarado.
5. El botón "Mostrar" no se renderiza cuando `useCan("members.reveal")` es falso.
6. `HistoryAside` muestra para cada entrada la fecha formateada con `formatDateTime`, el usuario y la acción (`insert`, `update`, `delete`, `reveal`) en español; nunca intenta descifrar `before` ni `after`.
7. `HistoryAside` muestra estado vacío "Sin cambios registrados" y estado de error con reintento.

## Escenarios BDD

```gherkin
# language: es
Característica: Valor enmascarado e historial

  Escenario: Mostrar un documento
    Dado una ficha con el documento enmascarado "•••• 0304"
    Y un usuario con permiso para mostrar datos
    Cuando pulsa "Mostrar"
    Entonces se llama una vez a la acción de mostrar
    Y se ve el documento en claro
    Y a los 60 segundos vuelve a verse "•••• 0304"

  Escenario: Permiso denegado por el API
    Dado una ficha con el teléfono enmascarado
    Cuando el usuario pulsa "Mostrar" y el API responde 403
    Entonces se ve "No tienes permiso para ver este dato"
    Y el teléfono sigue enmascarado

  Escenario: Usuario sin permiso no ve el botón
    Dado un usuario para el que la matriz no permite mostrar datos
    Cuando abre la ficha
    Entonces no hay botón "Mostrar"

  Escenario: Historial con un dato cifrado modificado
    Dado una entrada de auditoría que cambió el teléfono
    Cuando se muestra el historial
    Entonces la entrada dice "Teléfono: dato cifrado modificado"
    Y no se muestra ningún blob ni valor
```

## Endpoints

- Ninguno propio; la feature conecta `onReveal` a `POST /api/v1/members/{id}/reveal` (US-074) y el historial a `GET /api/v1/members/{id}/audit` (US-106).

## Pantalla

- Patrón `P_Ficha`; consumidores en `Socio_Ficha` (US-073, US-074, US-106) y `Atleta_Perfil` (US-179).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `maskValue` para documento, teléfono, correo, vacío.
- **Pruebas:** Testing Library con temporizadores falsos (60 s), verificación de que no se escribe en `localStorage`, `axe`.
- **Archivos principales:** `web/src/shared/ui/MaskedValue.tsx`, `HistoryAside.tsx`.

## Supuestos

- Supuesto: el valor en claro se vuelve a enmascarar a los 60 segundos; no está en las fuentes y se puede negociar.
- Supuesto: el enmascarado lo calcula el API (por ejemplo, últimos 4 dígitos del documento); el front no recibe el valor completo para enmascarar.

## Dependencias

- US-010 · Componentes base Button, Field, StatusTag.

## INVEST

- **Independiente:** se prueba con funciones simuladas.
- **Negociable:** tiempo de re-enmascarado y formato de máscara.
- **Valiosa:** garantiza RN-13 en pantalla.
- **Estimable:** dos componentes.
- **Pequeña:** 2 a 3 días.
- **Testeable:** llamadas, tiempos y ausencia de persistencia verificables.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales (si aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible (si aplica)
- [ ] `docs/openapi.json` regenerado (si cambia el contrato)
- [ ] Auditoría verificada para las tablas tocadas (si aplica)
- [ ] Revisión de PR aprobada
