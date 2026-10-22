"""Módulo de planes (EP-08; S2-B9 US-078 crear plan, US-079 listar planes).

Tabla `plans.plans` (migración `0007_plans`): nombre (único sin distinguir mayúsculas entre los
vivos, S2-D32), precio entero en COP, tipo (`days` o `classes`), duración en días, número de
clases (solo `classes`) y `is_active`. Borrado lógico (`deleted_at`). Sin columnas cifradas.
Otros módulos (`memberships`, Sprint 3) lo usan solo por `service.py` (`get`,
`get_including_deleted`, `names_for`), que devuelven `PlanSnapshot` o tipos simples y nunca el
ORM.
"""
