import { LayoutGrid, List } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ModViewMode } from "@/stores/ui-store";

interface Props {
  mode: ModViewMode;
  onChange: (mode: ModViewMode) => void;
  className?: string;
}

export function ViewModeToggle({ mode, onChange, className }: Props) {
  return (
    <div
      role="group"
      aria-label="View mode"
      className={cn(
        "inline-flex items-center rounded-lg border border-border bg-surface-2 p-0.5",
        className,
      )}
    >
      <button
        type="button"
        onClick={() => onChange("grid")}
        aria-pressed={mode === "grid"}
        title="Grid view (big previews)"
        className={cn(
          "rounded-md p-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
          mode === "grid"
            ? "bg-surface-0 text-text-primary shadow-sm"
            : "text-text-muted hover:text-text-secondary",
        )}
      >
        <LayoutGrid size={14} />
      </button>
      <button
        type="button"
        onClick={() => onChange("list")}
        aria-pressed={mode === "list"}
        title="List view (compact rows)"
        className={cn(
          "rounded-md p-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
          mode === "list"
            ? "bg-surface-0 text-text-primary shadow-sm"
            : "text-text-muted hover:text-text-secondary",
        )}
      >
        <List size={14} />
      </button>
    </div>
  );
}
