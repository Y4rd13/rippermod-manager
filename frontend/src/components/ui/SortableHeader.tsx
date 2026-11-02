import { ArrowDown, ArrowUp } from "lucide-react";

import { cn } from "@/lib/utils";

interface SortableHeaderProps {
  label: string;
  sortKey: string;
  activeSortKey: string;
  sortDir: "asc" | "desc";
  onSort: (key: string) => void;
  className?: string;
  align?: "left" | "right";
}

export function SortableHeader({
  label,
  sortKey,
  activeSortKey,
  sortDir,
  onSort,
  className,
  align = "left",
}: SortableHeaderProps) {
  const isActive = sortKey === activeSortKey;
  const Icon = sortDir === "asc" ? ArrowUp : ArrowDown;

  return (
    <th
      scope="col"
      aria-sort={isActive ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
      className={cn(
        "pb-2 pr-4 font-medium select-none",
        align === "right" && "text-right",
        className,
      )}
    >
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          "inline-flex items-center gap-0.5 rounded font-medium transition-colors",
          isActive ? "text-accent-text" : "text-text-muted hover:text-text-primary",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        )}
      >
        {label}
        {isActive && <Icon size={10} />}
      </button>
    </th>
  );
}
