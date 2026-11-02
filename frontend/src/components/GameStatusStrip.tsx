import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export interface StatusItem {
  key: "scanned" | "managed" | "matched" | "updates" | "conflicts" | "frameworks" | "health";
  label: string;
  value: string;
  tone?: "neutral" | "success" | "warning" | "danger";
  icon: LucideIcon;
  onSelect: () => void;
  title?: string;
}

const TONE_TEXT: Record<NonNullable<StatusItem["tone"]>, string> = {
  neutral: "text-text-primary",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
};

const TONE_ICON: Record<NonNullable<StatusItem["tone"]>, string> = {
  neutral: "text-text-muted",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
};

/**
 * One-line game status: each item is a button with icon, value and label that jumps to the
 * matching tab. Items wrap to a second line in narrow windows and never truncate.
 */
export function GameStatusStrip({ items }: { items: StatusItem[] }) {
  return (
    <div
      role="group"
      aria-label="Game status"
      className="flex flex-wrap items-center gap-y-1 rounded-xl border border-border bg-surface-1 px-0.5 py-0.5"
    >
      {items.map(({ key, label, value, tone = "neutral", icon: Icon, onSelect, title }) => (
        <button
          key={key}
          type="button"
          onClick={onSelect}
          title={title}
          className="inline-flex h-8 items-center gap-1 whitespace-nowrap rounded-lg px-1.5 text-sm transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <Icon size={13} aria-hidden="true" className={cn("shrink-0", TONE_ICON[tone])} />
          <span className={cn("text-[13px] font-semibold tabular-nums", TONE_TEXT[tone])}>{value}</span>
          <span className="text-[11px] text-text-muted">{label}</span>
        </button>
      ))}
    </div>
  );
}
