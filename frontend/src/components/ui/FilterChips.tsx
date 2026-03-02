import { cn } from "@/lib/utils";

interface Chip {
  key: string;
  label: string;
  count?: number;
}

interface SingleSelectProps {
  chips: Chip[];
  active: string;
  onChange: (key: string) => void;
  multi?: false;
  activeKeys?: never;
  onToggle?: never;
}

interface MultiSelectProps {
  chips: Chip[];
  multi: true;
  activeKeys: ReadonlySet<string>;
  onToggle: (key: string) => void;
  active?: never;
  onChange?: never;
}

type FilterChipsProps = SingleSelectProps | MultiSelectProps;

export function FilterChips(props: FilterChipsProps) {
  const { chips, multi } = props;
  return (
    <div className="flex items-center gap-1.5 overflow-x-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
      {chips.map((chip) => {
        const isActive = multi
          ? props.activeKeys.has(chip.key)
          : props.active === chip.key;
        return (
          <button
            key={chip.key}
            onClick={() => multi ? props.onToggle(chip.key) : props.onChange(chip.key)}
            className={cn(
              "shrink-0 rounded-full px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 focus-visible:ring-offset-surface-0",
              isActive
                ? "bg-accent text-white"
                : "bg-surface-2 text-text-muted hover:bg-surface-3 hover:text-text-secondary",
            )}
          >
            {chip.label}
            {chip.count != null && (
              <span className="ml-1 tabular-nums opacity-70">{chip.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
