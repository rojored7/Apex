"""`EXPLAIN (ANALYZE, BUFFERS)` de las consultas que dispara una prueba `perf` (V8, Sprint 6).

`capturar_sql(session, contiene)` anota los SELECT que la sesion envia y mencionan `contiene`;
`imprimir_explain(session, titulo, capturadas)` los ejecuta con `EXPLAIN (ANALYZE, BUFFERS)` e
imprime el plan completo y una linea de resumen (nodos de indice o `Seq Scan`, tiempo). No afirma
nada sobre el plan: solo deja la evidencia en la salida de `pytest -s`.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

Capturada = tuple[str, Any]
_TIEMPO = re.compile(r"Execution Time: ([\d.]+) ms")


@contextmanager
def capturar_sql(session: AsyncSession, contiene: str) -> Iterator[list[Capturada]]:
    """Los `SELECT`/`WITH` que la sesion ejecuta dentro del bloque y que contienen `contiene`."""
    capturadas: list[Capturada] = []
    destino = session.sync_session.get_bind()

    def anotar(_c: Any, _cur: Any, sql: str, parametros: Any, *_a: Any) -> None:
        if contiene in sql and sql.lstrip().upper().startswith(("SELECT", "WITH")):
            capturadas.append((sql, parametros))

    event.listen(destino, "before_cursor_execute", anotar)
    try:
        yield capturadas
    finally:
        event.remove(destino, "before_cursor_execute", anotar)


async def imprimir_explain(
    session: AsyncSession, titulo: str, capturadas: list[Capturada]
) -> list[str]:
    """Imprime el plan de cada consulta capturada y devuelve los resumenes (uno por consulta)."""
    assert capturadas, f"{titulo}: no se capturo ninguna consulta"
    conexion = await session.connection()
    resumenes: list[str] = []
    for n, (sql, parametros) in enumerate(capturadas, start=1):
        resultado = await conexion.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS) " + sql, parametros)
        lineas = [str(f[0]) for f in resultado.all()]
        plan = "\n".join(lineas)
        indices = sorted(
            set(re.findall(r"(?:Index(?: Only)? Scan|Bitmap Index Scan) (?:using |on )(\S+)", plan))
        )
        tiempo = _TIEMPO.search(plan)
        resumen = (
            f"{titulo} [{n}/{len(capturadas)}]: "
            f"{'indices ' + ', '.join(indices) if indices else 'sin indice'}; "
            f"Seq Scan={'si' if 'Seq Scan' in plan else 'no'}; "
            f"ejecucion {tiempo.group(1) if tiempo else '?'} ms"
        )
        print(
            f"\nEXPLAIN (ANALYZE, BUFFERS) {titulo} [{n}/{len(capturadas)}]\n{plan}\n=> {resumen}"
        )
        resumenes.append(resumen)
    return resumenes
