# US-065 · Como equipo quiero el panel lateral y el modal de confirmación con motivo para que crear, editar y anular se hagan con el mismo patrón en todo el sistema

- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context:** presentación (`web/src/shared/ui/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Patrón `P_Formulario` (referencia; lo usan `Planes`, `Pagos`, `Membresias`, `Usuarios`, `Socio_Ficha`)

## Historia

Como equipo
quiero `SidePanel` y `ConfirmModal` (con motivo obligatorio opcional)
para que registrar un pago, editar un plan, anular un pago o dar de baja un socio sigan el mismo flujo accesible y exijan motivo cuando la regla lo pide

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** motivo obligatorio al anular pago (RN-02), al anular membresía (`cancel(reason)`), al omitir aviso (RN-17 y EP-14); confirmación explícita en acciones irreversibles.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** No aplica.
- **Front:** `SidePanel` (se abre desde la derecha, título, cuerpo con formulario, pie con Cancelar y Guardar, ancho completo en celular, cierra con Escape salvo con cambios sin guardar); `ConfirmModal` (título, texto de consecuencia, campo de motivo opcional u obligatorio con longitud mínima, texto de confirmación tecleado opcional como "ROTAR", botón destructivo, estado enviando y error del API dentro del modal).

## Criterios de aceptación

1. Ambos componentes atrapan el foco mientras están abiertos, lo devuelven al elemento que los abrió al cerrarse y tienen `role="dialog"` con `aria-modal="true"` y título asociado.
2. `SidePanel` con cambios sin guardar pide confirmación antes de cerrar por Escape, por el botón Cancelar o por clic fuera.
3. `ConfirmModal` con `reasonRequired` deshabilita el botón de confirmar mientras el motivo esté vacío o tenga solo espacios.
4. `ConfirmModal` con `confirmText="ROTAR"` deshabilita el botón hasta que el texto tecleado coincida exactamente.
5. Mientras la petición está en curso el botón muestra estado de envío y no admite un segundo clic (evita doble anulación).
6. Si el API responde con error, el modal sigue abierto y muestra el `message` del envelope; si trae `field = "reason"`, el error se muestra en el campo de motivo.
7. Los botones destructivos usan el token de peligro y llevan texto explícito ("Anular pago", "Dar de baja"), nunca solo un icono.

## Escenarios BDD

```gherkin
# language: es
Característica: Panel lateral y modal de confirmación

  Escenario: Anular con motivo
    Dado un modal de anulación con motivo obligatorio
    Cuando el usuario escribe "Pago duplicado" y confirma
    Entonces se envía la acción con el motivo "Pago duplicado"
    Y el modal se cierra al recibir respuesta exitosa

  Escenario: Motivo vacío
    Dado un modal de anulación con motivo obligatorio
    Cuando el usuario escribe solo espacios
    Entonces el botón de confirmar está deshabilitado

  Escenario: Error del API dentro del modal
    Dado un modal de anulación abierto
    Cuando el API responde 422 con field "reason"
    Entonces el modal sigue abierto
    Y el error se muestra debajo del campo de motivo

  Escenario: Doble clic en confirmar
    Dado un modal con la petición en curso
    Cuando el usuario pulsa confirmar otra vez
    Entonces no se envía una segunda petición

  Escenario: Cerrar el panel con cambios
    Dado un panel lateral con un campo modificado
    Cuando el usuario pulsa Escape
    Entonces se le pregunta si descarta los cambios
```

## Endpoints

- Ninguno.

## Pantalla

- `P_Formulario` como referencia; consumidores: registro de pago (US-095), crear y editar plan (US-078, US-080), anular pago (US-097), anular membresía (US-090), dar de baja socio (US-076), crear usuario (US-047).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** Testing Library (foco atrapado, Escape, motivo, texto de confirmación, doble envío), `axe`.
- **Archivos principales:** `web/src/shared/ui/SidePanel.tsx`, `ConfirmModal.tsx`.

## Supuestos

- Supuesto: longitud mínima del motivo de 3 caracteres no vacíos en el front; el API valida "no vacío" (la regla de dominio solo exige no vacío).

## Dependencias

- US-010 · Componentes base Button, Field, StatusTag.

## INVEST

- **Independiente:** sin API.
- **Negociable:** longitud mínima del motivo y comportamiento de clic fuera.
- **Valiosa:** protege acciones irreversibles con un patrón único.
- **Estimable:** dos componentes de diálogo.
- **Pequeña:** 2 a 3 días.
- **Testeable:** comportamiento de foco y validación verificable.

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
