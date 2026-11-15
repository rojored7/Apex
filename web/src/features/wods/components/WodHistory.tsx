// S8-F3 · E5 (front): «Historial» del WOD con HistoryAside sobre GET /audit?table=wods.wods&record_id= (solo `audit.view`: admin).
import { useState } from "react";
import { HistoryAside } from "../../../shared/ui/HistoryAside";
import { toEntry, useWodHistory } from "../historyApi";

export function WodHistory({ wodId }: { wodId: string }) {
  const [pages, setPages] = useState(1);
  const history = useWodHistory(wodId, pages);
  const items = history.data?.items ?? [];
  return (
    <HistoryAside
      title="Historial"
      entries={items.map(toEntry)}
      total={history.data?.total ?? 0}
      isLoading={history.isLoading}
      error={history.isError ? history.error : undefined}
      onRetry={() => {
        void history.refetch();
      }}
      moreLabel="Cargar más"
      onLoadMore={() => {
        setPages((current) => current + 1);
      }}
    />
  );
}
