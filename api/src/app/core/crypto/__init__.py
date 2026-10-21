"""El bus de criptografía (CLAUDE.md). Única puerta de las primitivas.

- `digest.py`: SHA-256 sin llave, para la cadena de auditoría (US-015, N-06).
- `bus.py`: `encrypt`, `decrypt`, `blind_index`, `sign`, `verify` y `digest` (US-025 a US-029).
- `providers/`: `KeyProvider` local y OpenBao (US-023, v0.2).
"""
