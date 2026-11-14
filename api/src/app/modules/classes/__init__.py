"""Módulo de clases (EP-21; S7-A2 US-155 franjas del horario).

Esquema `classes` (migración `0026_class_slots`): `class_slots` (una franja es UNA fila con varios
días). En B1, C1 y siguientes suma `class_sessions` y `attendance`. Otros módulos lo usan solo por
`service.py`. Archivos privados: `rules`, `slots`, `events` (más `sessions`, `attendance`,
`queries` y `reports` cuando existan).
"""
