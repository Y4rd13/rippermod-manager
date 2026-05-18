import { Grid3x3, LayoutGrid, List } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ModViewMode } from "@/stores/ui-store";

interface Props {
  mode: ModViewMode;
  onChange: (mode: ModViewMode) => void;
  className?: string;
}

const MODES: { value: ModViewMode; icon: typeof List; title: string }[] = [
  { value: "grid", icon: LayoutGrid, title: "Grid view (big previews)" },
  { value: "compact", icon: Grid3x3, title: "Compact tiles (small)" },
  { value: "list", icon: List, title: "List view (rows)" },
];

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
      {MODES.map(({ value, icon: Icon, title }) => (
        <button
          key={value}
          type="button"
          onClick={() => onChange(value)}
          aria-pressed={mode === value}
          title={title}
          className={cn(
            "rounded-md p-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
            mode === value
              ? "bg-surface-0 text-text-primary shadow-sm"
              : "text-text-muted hover:text-text-secondary",
          )}
        >
          <Icon size={14} />
        </button>
      ))}
    </div>
  );
}
