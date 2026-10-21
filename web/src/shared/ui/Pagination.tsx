// US-063 T5: tamaño de página (25, 50, 100), tramo, página actual y anterior/siguiente.
// Siempre trabaja con limit y offset (D2); la página es solo presentación.
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useId } from "react";
import { PAGE_SIZES, offsetToPage, rangeLabel, totalPages } from "../lib/pagination";
import { Button } from "./Button";
import styles from "./Pagination.module.css";

export interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onPageChange: (page: number) => void;
  onLimitChange: (limit: number) => void;
}

export function Pagination({ total, limit, offset, onPageChange, onLimitChange }: PaginationProps) {
  const sizeId = useId();
  const page = offsetToPage(offset, limit);
  const pages = totalPages(total, limit);
  // Un limit válido de la URL que no es estándar (por ejemplo 30) se muestra tal cual.
  const sizes = [...new Set<number>([...PAGE_SIZES, limit])].sort((a, b) => a - b);

  return (
    <nav aria-label="Paginación" className={styles.pagination}>
      <div className={styles.size}>
        <label htmlFor={sizeId} className={styles.label}>
          Mostrar
        </label>
        <select
          id={sizeId}
          className={styles.select}
          value={String(limit)}
          onChange={(event) => {
            onLimitChange(Number(event.target.value));
          }}
        >
          {sizes.map((size) => (
            <option key={size} value={String(size)}>
              {size}
            </option>
          ))}
        </select>
      </div>
      <span className={styles.range}>{rangeLabel(offset, limit, total)}</span>
      <span className={styles.spacer} />
      <Button
        variant="secondary"
        disabled={total === 0 || page <= 1}
        onClick={() => {
          onPageChange(page - 1);
        }}
      >
        <ChevronLeft size={20} aria-hidden="true" />
        Anterior
      </Button>
      <span className={styles.page}>{`Página ${String(page)} de ${String(pages)}`}</span>
      <Button
        variant="secondary"
        disabled={total === 0 || page >= pages}
        onClick={() => {
          onPageChange(page + 1);
        }}
      >
        Siguiente
        <ChevronRight size={20} aria-hidden="true" />
      </Button>
    </nav>
  );
}
