"""Tablero de Inicio (S4A-B8; US-108, US-110; S4A-D27 a S4A-D29).

Módulo de lectura: sin `models.py` y sin SQL propio. Compone los services de `memberships`
(resumen), `payments` (ingresos del mes), `audit` (`recent`), `members` (nombres), `auth`
(`user_names_for`) y nunca `plans` (el plan sale de `memberships.refs_for`).
"""
