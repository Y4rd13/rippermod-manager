import { useMemo, useState } from "react";

export function useBulkSelect<K extends string | number>(allIds: K[]) {
  const [selectedIds, setSelectedIds] = useState<Set<K>>(new Set());

  const validSelected = useMemo(() => {
    const idSet = new Set(allIds);
    const pruned = new Set<K>();
    for (const id of selectedIds) {
      if (idSet.has(id)) pruned.add(id);
    }
    return pruned.size !== selectedIds.size ? pruned : selectedIds;
  }, [allIds, selectedIds]);

  const isSelected = useMemo(() => {
    return (id: K) => validSelected.has(id);
  }, [validSelected]);

  const toggle = (id: K) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelectedIds(new Set(allIds));
  const deselectAll = () => setSelectedIds(new Set());

  return {
    selectedIds: validSelected,
    isSelected,
    toggle,
    selectAll,
    deselectAll,
    selectedCount: validSelected.size,
    isAllSelected: allIds.length > 0 && validSelected.size === allIds.length,
  };
}
