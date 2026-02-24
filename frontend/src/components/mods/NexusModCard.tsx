import { Heart, User } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const PLACEHOLDER_IMG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='320' height='180' fill='%231a1a2e'%3E%3Crect width='320' height='180'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%23555' font-size='14'%3ENo Image%3C/text%3E%3C/svg%3E";

interface Props {
  modName: string;
  summary?: string;
  author?: string;
  version?: string;
  endorsementCount?: number;
  pictureUrl?: string;
  action?: ReactNode;
  footer?: ReactNode;
  badge?: ReactNode;
  overflowMenu?: ReactNode;
  onClick?: () => void;
  onContextMenu?: React.MouseEventHandler;
}

export function NexusModCard({
  modName,
  summary,
  author,
  version,
  endorsementCount,
  pictureUrl,
  action,
  footer,
  badge,
  overflowMenu,
  onClick,
  onContextMenu,
}: Props) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-surface-1 overflow-hidden flex flex-col",
        badge ? "border-warning/40" : "border-border",
        onClick && "cursor-pointer hover:border-accent/40 transition-colors",
      )}
      onClick={onClick}
      onContextMenu={onContextMenu}
    >
      <div className="relative">
        <img
          src={pictureUrl || PLACEHOLDER_IMG}
          alt={modName}
          loading="lazy"
          className="w-full h-40 object-cover bg-surface-2"
          onError={(e) => {
            (e.target as HTMLImageElement).src = PLACEHOLDER_IMG;
          }}
        />
        {badge && (
          <div className="absolute top-2 right-2">{badge}</div>
        )}
      </div>

      <div className="p-4 flex flex-col flex-1 gap-2">
        <h3 className="text-sm font-semibold text-text-primary leading-tight line-clamp-2" title={modName}>
          {modName}
        </h3>

        {summary && (
          <p className="text-xs text-text-muted line-clamp-2" title={summary}>{summary}</p>
        )}

        <div className="flex items-center gap-3 text-xs text-text-muted mt-auto pt-1">
          {author && (
            <span className="flex items-center gap-1 truncate" title={author}>
              <User size={12} />
              {author}
            </span>
          )}
          {version && <span className="truncate" title={`v${version}`}>v{version}</span>}
          {endorsementCount != null && endorsementCount > 0 && (
            <span className="flex items-center gap-1" title={`${endorsementCount.toLocaleString()} endorsements on Nexus`}>
              <Heart size={12} />
              {endorsementCount.toLocaleString()}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-border/50">
          <div className="min-w-0 flex-1">{footer ?? <div />}</div>
          <div className="flex items-center gap-1 shrink-0 ml-auto">
            {action}
            {overflowMenu}
          </div>
        </div>
      </div>
    </div>
  );
}
