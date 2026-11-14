# Crítica 2 del plan del Sprint 7 (plan-critic, 2026-11-14)

Veredicto: RECHAZADO (ediciones locales; no cambia el orden de los slices)

Los 12 hallazgos de la crítica 1 quedaron resueltos. Las correcciones abren cuatro problemas:

1. ALTO · `on_date = session_date` reabre H-3 (sesión futura descuenta de una tiquetera que aún no empieza) y el recorte `max(start_date, hoy)` alarga una membresía vencida al agotarla desde una sesión pasada (choque con `ex_memberships_member_dates`, `0008_memberships.py:17-18, 206-209`). Corrección en C2: `on_date = min(session_date, hoy_bogota())`; `end_date = min(end_date, max(start_date, hoy))`; pruebas `test_sesion_futura_no_usa_tiquetera_futura` y `test_agotar_vencida_no_alarga_end_date`.
2. ALTO · el rollback real con `deploy_e2e.sh` en W0-3 punto 6 y V3 no es ejecutable (prod-smoke baja `apex-smoke` al salir; desplegar v0.3.0 pisa `apex-api:local` y `apex-web:local` del daemon compartido; el auxiliar no tiene la etiqueta; falta `alembic downgrade 0024`).
3. MEDIO · «variable vacía» es ambiguo: con `CRYPTO_LOCAL_SIGNING_KEY_PATH=` la ruta vale `Path(".")` (sin `env_ignore_empty`, `config.py:193-199`); la línea comentada rompe `test_toda_variable_de_settings_esta_documentada` (`test_env_example.py:34-37`). Corrección: «sin línea», la preverificación de v0.4 rechaza `^CRYPTO_LOCAL_SIGNING_KEY_PATH=$`, validador o `env_ignore_empty`, excepción con motivo y `test_firma_con_linea_vacia_aborta`.
4. MEDIO · W0-4 debe renombrar y actualizar `test_el_comentario_del_catalogo_dice_23_cubetas_y_22_variables` (línea 431) y `test_ci_sube_las_veintidos_variables_user_y_cuenta_veintidos` (línea 487).
5. BAJO · borrar la cita «`sed` de 352-366» de W0-4.

## Resolución del orquestador

Se alcanzó el máximo de dos rondas del flujo; las cinco son ediciones locales y se aplican tal como las propone la crítica. Para el hallazgo 2 se toma la alternativa que la crítica ofrece: la preverificación de v0.3 sobre `.env` se prueba con `test_deploy_script.sh` y sus falsos (sin desplegar v0.3.0 en el daemon compartido) y el rollback real queda documentado paso a paso en el RUNBOOK §12. Con esas ediciones el plan queda aprobado para ejecutarse por la orden del usuario del 2026-11-14 («no pare hasta terminar»).
