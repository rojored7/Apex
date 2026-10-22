"""Módulo de socios (EP-07; S2-B7 US-069 registrar socio, S2-B8 US-070 buscar y listar).

Tabla `members.members` (migración `0006_members`): nombres en claro (van al leaderboard),
cinco campos cifrados por el bus (`member.document`, `member.phone`, `member.email`,
`member.birth_date`, `member.emergency_contact`) y tres índices ciegos. Sin `notes` (M-5).
Otros módulos lo usan solo por `service.py` (`get_ref`, `ensure_exists`, `id_by_document`,
`count`), que devuelven dataclasses de `schemas.py` y nunca el ORM.
"""
