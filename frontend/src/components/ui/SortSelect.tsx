import { ArrowDownAZ, ArrowUpAZ } from "lucide-react";

import { cn } from "@/lib/utils";

interface SortOption {
  value: string;
  label: string;
}

type SortDir = "asc" | "desc";

interface SortSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SortOption[];
  className?: string;
  sortDir?: SortDir;
  onSortDirChange?: (dir: SortDir) => void;
}

export function SortSelect({ value, onChange, options, className, sortDir, onSortDirChange }: SortSelectProps) {
  return (
    <div className="flex items-center gap-1">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 focus-visible:ring-offset-surface-0",
          className,
        )}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {onSortDirChange && sortDir && (
        <button
          onClick={() => onSortDirChange(sortDir === "asc" ? "desc" : "asc")}
          aria-label={sortDir === "asc" ? "Sort descending" : "Sort ascending"}
          title={sortDir === "asc" ? "Sort descending" : "Sort ascending"}
          className="rounded-lg border border-border bg-surface-2 p-1.5 text-text-muted hover:text-text-primary hover:bg-surface-3 transition-colors focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 focus-visible:ring-offset-surface-0 focus:outline-none"
        >
          {sortDir === "asc" ? <ArrowDownAZ size={16} /> : <ArrowUpAZ size={16} />}
        </button>
      )}
    </div>
  );
}
