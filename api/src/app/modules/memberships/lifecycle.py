"""Ciclo de vida de una membresía (privado, D7): congelar (B2), anular (B6) y los handlers de
pagos `on_payment_registered` y `on_payment_voided` (B4 y B5).

Regla de candados (S3-D43, `tests/architecture/test_handlers_no_new_locks.py`): un handler `on_*`
solo vuelve a pedir la fila que el emisor ya tiene (`sell.lock_membership` con
`event.membership_id`); nunca el candado del socio ni otro `FOR UPDATE`.
"""
