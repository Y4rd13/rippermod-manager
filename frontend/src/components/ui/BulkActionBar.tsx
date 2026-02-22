import type { ReactNode } from "react";

interface BulkActionBarProps {
  selectedCount: number;
  totalCount: number;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  isAllSelected: boolean;
  children: ReactNode;
}

export function BulkActionBar({
  selectedCount,
  totalCount,
  onSelectAll,
  onDeselectAll,
  isAllSelected,
  children,
}: BulkActionBarProps) {
  if (selectedCount === 0) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 rounded-xl border border-border bg-surface-1 shadow-2xl px-4 py-3 flex items-center gap-4 animate-fade-in">
      <span className="text-sm text-text-secondary tabular-nums whitespace-nowrap">
        {selectedCount} of {totalCount} selected
      </span>
      <button
        className="text-xs text-accent hover:text-accent-hover transition-colors whitespace-nowrap"
        onClick={isAllSelected ? onDeselectAll : onSelectAll}
      >
        {isAllSelected ? "Deselect all" : "Select all"}
      </button>
      <div className="h-4 w-px bg-border" />
      <div className="flex items-center gap-2">{children}</div>
    </div>
  );
}
