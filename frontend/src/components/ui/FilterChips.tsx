import { cn } from "@/lib/utils";

interface Chip {
  key: string;
  label: string;
  count?: number;
}

interface FilterChipsProps {
  chips: Chip[];
  active: string;
  onChange: (key: string) => void;
}

export function FilterChips({ chips, active, onChange }: FilterChipsProps) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {chips.map((chip) => (
        <button
          key={chip.key}
          onClick={() => onChange(chip.key)}
          className={cn(
            "rounded-full px-3 py-1 text-xs font-medium transition-colors",
            active === chip.key
              ? "bg-accent text-white"
              : "bg-surface-2 text-text-muted hover:bg-surface-3 hover:text-text-secondary",
          )}
        >
          {chip.label}
          {chip.count != null && (
            <span className="ml-1 tabular-nums opacity-70">{chip.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}
