"""Worker programado de APEX (US-113; S4A-D6): `python -m app.worker.main`.

Capa de aplicación como `cli.py`: importa `app.core.*` y, de los módulos, solo `service`,
`schemas` y `exceptions`; nunca `models`, `router` ni privados, y no escribe SQL
(`tests/architecture/test_worker_boundaries.py`, S4A-D10).
"""
