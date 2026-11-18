// V7 L6: pide páginas de un listado del api hasta cubrir `total` o llegar al tope de páginas, sin repetir una fila.
// Lo usan el catálogo (opciones de los selects) y los benchmarks del atleta (los chips): una sola regla de paginación.
export interface CollectPagesOptions<R> {
  /** Tamaño de página que se pide (el api topa en 200). */
  limit: number;
  /** Tope de páginas: más allá la lista queda incompleta y `truncated` lo dice. */
  maxPages: number;
  /** La identidad de una fila: una fila que se mueve entre páginas durante la lectura se cuenta una sola vez. */
  idOf: (row: R) => string;
}

export interface CollectedPages<R> {
  items: R[];
  total: number;
  /** Hay más filas que las que caben en `maxPages` páginas. */
  truncated: boolean;
}

export async function collectPages<R>(fetchPage: (offset: number) => Promise<{ items: readonly R[]; total: number }>, options: CollectPagesOptions<R>): Promise<CollectedPages<R>> {
  const rows = new Map<string, R>();
  let total = 0;
  for (let page = 0; page < options.maxPages; page += 1) {
    const offset = page * options.limit;
    if (page > 0 && offset >= total) break;
    const result = await fetchPage(offset);
    total = result.total;
    for (const row of result.items) {
      const id = options.idOf(row);
      if (!rows.has(id)) rows.set(id, row);
    }
  }
  return { items: [...rows.values()], total, truncated: total > options.maxPages * options.limit };
}
