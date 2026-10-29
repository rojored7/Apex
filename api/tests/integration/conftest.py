"""Fixtures de `tests/integration` (S4A-D67, nace en S4A-B7).

Pruebas que cruzan módulos por sus `service.py` reales (por ejemplo `plans` y `memberships`) sobre
PostgreSQL. Usan las fixtures de `tests/conftest.py`; aquí no hay ninguna propia todavía.
`run-gates.sh` y la CI las recogen sin cambios (recorren `tests/`).
"""
