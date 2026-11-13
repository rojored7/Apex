// S6-F2 · US-143 (Llaves.html, pestaña Inventario; S6-D13, S6-D16): inventario de llaves de cifrado.
// - DataTable paginada en el servidor (limit/offset en la URL, 25/50/100) con la búsqueda por clase de dato (viaja
//   al api como `q`; no queda en la URL ni en la caché, `gcTime: 0`) y los filtros Propósito, Estado y Proveedor en la URL con los nombres del api;
//   cryptoFilters decide qué viaja (un valor ajeno no).
// - Estado con StatusTag de texto, fechas en hora de Bogotá, `records_count` o «n/a» (índice y firma no tienen
//   registros que contar) y «Rotar» solo en filas activas de propósito `encrypt` (canRotate): una `index` o
//   `sign` no se rota desde aquí (409 purpose_not_rotatable) y una vieja ya no es la vigente.
// - Nunca se pinta material de llave: el contrato no lo trae y el esquema `.strict()` rechaza campos extra.
// DESIGN-GAP: Llaves.html tiene las columnas «Dónde vive» y «Límite» y los enlaces «Ver tarea» y «Ver»; el api
// no publica el límite de rotación (solo `age_days`, que se muestra como «Antigüedad») ni se necesita la
// ubicación del material (siempre «envuelta» en crypto_keys): «Dónde vive» pasa a «Proveedor» y «Ver tarea»
// vive en la pestaña Trabajos (BRECHAS 14.7).
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { formatCount, formatDateTime } from "../../../core/i18n/format";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { FilterBar, type FilterOption } from "../../../shared/ui/FilterBar";
import { Pagination } from "../../../shared/ui/Pagination";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { cryptoLabel } from "../../../shared/ui/statusLabel";
import { useCryptoKeys } from "../api";
import { KEYS_FILTERS, readKeysFilters, toKeysApiParams, type KeysFilter } from "../cryptoFilters";
import { PROVIDER_LABELS, PURPOSE_LABELS, canRotate } from "../cryptoLabels";
import { keysListError } from "../keysErrors";
import { KEY_PROVIDERS, KEY_PURPOSES, KEY_STATES, type CryptoKeyView } from "../schemas";
import { RotateKeyModal } from "./RotateKeyModal";
import styles from "./KeysInventory.module.css";

export const KEYS_EMPTY_FILTERED = "No hay llaves con estos filtros";
export const KEYS_EMPTY = "Todavía no hay llaves registradas. Las crea el sistema al arrancar (init-keys); si acabas de instalar, revisa el RUNBOOK.";
const NOT_APPLICABLE = "n/a";
const NO_DATE = "—";

const PURPOSE_OPTIONS: FilterOption[] = KEY_PURPOSES.map((value) => ({ value, label: PURPOSE_LABELS[value] }));
const STATE_OPTIONS: FilterOption[] = KEY_STATES.map((value) => ({ value, label: cryptoLabel(value) }));
const PROVIDER_OPTIONS: FilterOption[] = KEY_PROVIDERS.map((value) => ({ value, label: PROVIDER_LABELS[value] }));

const isFilter = (name: string): name is KeysFilter => (KEYS_FILTERS as readonly string[]).includes(name);

function ageText(days: number): string {
  return days === 1 ? "1 día" : `${formatCount(days)} días`;
}

function columns(onRotate: (key: CryptoKeyView) => void): Column<CryptoKeyView>[] {
  return [
    {
      key: "data_class",
      header: "Clase de dato",
      render: (key) => (
        <span className={styles.cls}>
          <span className={styles.name}>{key.data_class}</span>
          <span className={styles.note}>{PURPOSE_LABELS[key.purpose]}</span>
        </span>
      ),
    },
    { key: "algorithm", header: "Algoritmo", render: (key) => key.algorithm },
    { key: "provider", header: "Proveedor", render: (key) => PROVIDER_LABELS[key.provider] },
    { key: "version", header: "Versión", render: (key) => `v${String(key.version)}` },
    { key: "created_at", header: "Creada", render: (key) => <span className={styles.nowrap}>{formatDateTime(key.created_at)}</span> },
    { key: "rotated_at", header: "Última rotación", render: (key) => (key.rotated_at ? <span className={styles.nowrap}>{formatDateTime(key.rotated_at)}</span> : NO_DATE) },
    { key: "age_days", header: "Antigüedad", render: (key) => ageText(key.age_days) },
    { key: "records_count", header: "Registros", align: "end", render: (key) => (key.records_count === null ? NOT_APPLICABLE : formatCount(key.records_count)) },
    { key: "state", header: "Estado", render: (key) => <StatusTag crypto={key.state} /> },
    {
      key: "actions",
      header: "Acción",
      align: "end",
      wide: true,
      render: (key) =>
        canRotate(key) ? (
          <Button
            variant="secondary"
            aria-label={`Rotar ${key.data_class}`}
            onClick={() => {
              onRotate(key);
            }}
          >
            Rotar
          </Button>
        ) : null,
    },
  ];
}

export function KeysInventory() {
  const list = useListParams<KeysFilter>({ filters: KEYS_FILTERS, localQuery: true });
  const [searchParams] = useSearchParams();
  const search = searchParams.toString();
  const { q } = list;
  const filters = useMemo(() => readKeysFilters(search), [search]);
  const params = useMemo(() => toKeysApiParams(search, q), [search, q]);
  const keys = useCryptoKeys(params);
  const [target, setTarget] = useState<CryptoKeyView | null>(null);
  const columnList = useMemo(() => columns(setTarget), []);
  const limit = Number(params.get("limit"));
  const offset = Number(params.get("offset"));
  const page = keys.data;
  const isFiltered = q !== "" || KEYS_FILTERS.some((name) => filters[name] !== "");

  return (
    <div className={styles.root}>
      <FilterBar
        query={q}
        onQueryChange={list.setQuery}
        onClear={list.clear}
        searchLabel="Clase de dato"
        searchPlaceholder="member.document"
        selects={[
          { name: "purpose", label: "Propósito", value: filters.purpose, options: PURPOSE_OPTIONS },
          { name: "state", label: "Estado", value: filters.state, options: STATE_OPTIONS },
          { name: "provider", label: "Proveedor", value: filters.provider, options: PROVIDER_OPTIONS },
        ]}
        onSelectChange={(name, value) => {
          if (isFilter(name)) list.setFilter(name, value || undefined);
        }}
      />
      <DataTable
        caption="Inventario de llaves"
        columns={columnList}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(key) => key.id}
        isLoading={keys.isLoading || keys.isPlaceholderData}
        error={keysListError(keys.error)}
        onRetry={() => {
          void keys.refetch();
        }}
        emptyMessage={isFiltered ? KEYS_EMPTY_FILTERED : KEYS_EMPTY}
        emptyAction={
          isFiltered ? (
            <Button variant="secondary" onClick={list.clear}>
              Limpiar filtros
            </Button>
          ) : undefined
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      <p className={styles.help}>
        Nunca se muestra material de llave: solo metadatos. Una llave no se borra: pasa a «solo descifrar», luego a «retirada» y, cuando ya no quedan datos con esa versión, se destruye. Las llaves de índice y de firma no se rotan desde aquí.
      </p>
      <RotateKeyModal
        target={target}
        onClose={() => {
          setTarget(null);
        }}
      />
    </div>
  );
}
