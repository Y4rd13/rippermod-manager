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
      className={cn(
        "pb-2 pr-4 font-medium cursor-pointer select-none transition-colors",
        isActive ? "text-accent" : "text-text-muted hover:text-text-primary",
        align === "right" && "text-right",
        className,
      )}
      onClick={() => onSort(sortKey)}
    >
      <span className="inline-flex items-center gap-0.5">
        {label}
        {isActive && <Icon size={10} />}
      </span>
    </th>
  );
}
