import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const PLACEHOLDER_IMG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80' fill='%231a1a2e'%3E%3Crect width='80' height='80'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%23555' font-size='9'%3ENo Image%3C/text%3E%3C/svg%3E";

interface Props {
  modName: string;
  pictureUrl?: string;
  badge?: ReactNode;
  footer?: ReactNode;
  action?: ReactNode;
  onClick?: () => void;
  onContextMenu?: React.MouseEventHandler;
}

export function NexusModTile({
  modName,
  pictureUrl,
  badge,
  footer,
  action,
  onClick,
  onContextMenu,
}: Props) {
  return (
    <div
      className={cn(
        "relative flex flex-col rounded-lg border border-border bg-surface-1 overflow-hidden transition-colors",
        onClick && "cursor-pointer hover:border-accent/40 hover:bg-surface-2",
      )}
      onClick={onClick}
      onContextMenu={onContextMenu}
    >
      <div className="relative aspect-square w-full overflow-hidden bg-surface-2">
        <img
          src={pictureUrl || PLACEHOLDER_IMG}
          alt={modName}
          loading="lazy"
          className="h-full w-full object-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).src = PLACEHOLDER_IMG;
          }}
        />
        {badge && (
          <div className="absolute top-1 left-1 flex flex-wrap gap-1">{badge}</div>
        )}
      </div>
      <div className="flex flex-col gap-1 p-2 min-w-0">
        <h3
          className="text-xs font-medium text-text-primary line-clamp-2 leading-tight min-h-[2rem]"
          title={modName}
        >
          {modName}
        </h3>
        {footer && (
          <div className="flex items-center gap-1 text-[10px] text-text-muted">{footer}</div>
        )}
      </div>
      {action && (
        <div
          className="border-t border-border/50 p-1.5 flex items-center justify-center"
          onClick={(e) => e.stopPropagation()}
        >
          {action}
        </div>
      )}
    </div>
  );
}
