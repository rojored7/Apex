# ADRs

Registros de decisiones de arquitectura de APEX. Cada archivo nombra una decisión que no se cambia sin detenerse y preguntar.

| Archivo | Decisión |
|---|---|
| `ADR-001-monolito-modular.md` | Monolito modular: un api, un worker, una base con un esquema por módulo |
| `ADR-002-criptografia.md` | Bus de criptografía: formatos irreversibles (blob, AAD, índice ciego, KEK, rotación) |
| `ADR-003-pagos-inmutables.md` | Pagos inmutables: anulación en la fila, sin `DELETE`, trigger en la base |
| `ADR-004-serializacion-canonica-de-auditoria.md` | Serialización canónica y cadena de hashes de la auditoría, con vector de prueba |
| `ADR-005-custodia-openbao.md` | Custodia de la KEK con OpenBao Transit: una llave, tokens por servicio, desello 5/3, custodia 2/2/1 y snapshot firmado |

## Plantilla

Todo ADR nuevo lleva estas seis secciones, en este orden, cada una con contenido:

1. `## Estado`: aceptado, desde cuándo, y la frase de que cambiarlo exige detenerse y preguntar.
2. `## Contexto`: el problema y las fuerzas en juego.
3. `## Decisión`: lo que se hace, concreto.
4. `## Alternativas descartadas`: qué se consideró y por qué no.
5. `## Consecuencias`: lo que cuesta y lo que habilita.
6. `## Cómo se verifica`: las rutas `tests/...py` (relativas a `api/`) que lo fijan.

`api/tests/architecture/test_adr_docs.py` comprueba los nombres, las seis secciones, la frase y que cada ruta citada exista.
