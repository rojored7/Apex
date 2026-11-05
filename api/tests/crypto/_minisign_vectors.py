"""Vectores REALES de `minisign` 0.12 para `test_minisign.py` (S5-B13, Rojo).

Generados una sola vez dentro de `apex-backup:local` con `docker run --rm` (2026-11-04):

    minisign -G -W -f -p a.pub -s a.key        # y lo mismo para b (sin contraseña)
    minisign -S -s a.key -m data.json -x ed.minisig -t "timestamp:1700000000 file:data.json"
    minisign -S -l -s a.key -m data.json -x legacy.minisig -t "timestamp:1700000000 file:data.json"

Las llaves A y B son DESECHABLES y de prueba: se crearon en un contenedor efímero, sus secretas
se descartaron con él y no protegen nada. Solo se conservan las públicas y las firmas. `minisign
-V` verificó ambas firmas con la pública A al generarlas.
"""

from __future__ import annotations

from typing import Final

DATA: Final = b'{"vector": "apex-minisign-test", "n": 1}\n'

PUBKEY_A_LINE: Final = "RWQpBazLw8F5eWSQusHr6xq+6CZyQvhgYoCZPlnyI6w5jndJtE0E+hA0"
PUBKEY_A_FILE: Final = (
    "untrusted comment: minisign public key 7979C1C3CBAC0529\n" + PUBKEY_A_LINE + "\n"
)
PUBKEY_B_LINE: Final = "RWTJjBcjGzXX+0NdTTOoAU8R5e0Ulj/9Pz+MhVRbWf5T0Imy4Mxfgf5C"

TRUSTED_COMMENT: Final = "timestamp:1700000000 file:data.json"

SIG_ED: Final = (
    "untrusted comment: signature from minisign secret key\n"
    "RUQpBazLw8F5eab6hjoZhy+vUgzvvaOoY3fjEQcHhZs/EUNnvFyKvB4dfoHc1gqETgkrAZqMSNOboMfcXT0h5xC3"
    "M3elsVSXMAs=\n"
    "trusted comment: timestamp:1700000000 file:data.json\n"
    "6qLVyZj9Gy0/mad5OuQyY9mkM8bcVLNb1U+mUOQ1NCpRrMyBJPK2xoyjsruqwdIDIzYcURPiqI9/cSd5vGVPBQ==\n"
)

# Firma con el algoritmo `Ed` heredado (dato crudo, sin BLAKE2b): válida para minisign 0.12 con
# `-V`, pero APEX la rechaza (S5-D72).
SIG_LEGACY: Final = (
    "untrusted comment: signature from minisign secret key\n"
    "RWQpBazLw8F5eeCjVgQYL+fhd8nwQkegBN0KL5BzZBdcKrMU98fyMjFmYFlMlZL3hNPezfwdIBCWkNx4jpiOj1OC"
    "Zp5uDWf51wo=\n"
    "trusted comment: timestamp:1700000000 file:data.json\n"
    "oIBoCoiakHnpdUg/sSshwA3Avf8IxCUavV5tkEP3d+CeHfPVe+9X8N5p+chFCEWamCUo5HcYm5YfOVSxzUyACg==\n"
)
