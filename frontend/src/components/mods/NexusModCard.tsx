import { Heart, Package, User } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const PLACEHOLDER_IMG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48' fill='%231a1a2e'%3E%3Crect width='48' height='48'/%3E%3C/svg%3E";

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
      <div className="p-4 flex flex-col flex-1 gap-2">
        <div className="flex items-start gap-3">
          <img
            src={pictureUrl || PLACEHOLDER_IMG}
            alt=""
            loading="lazy"
            className="flex-shrink-0 w-12 h-12 rounded-lg object-cover bg-surface-2"
            onError={(e) => {
              (e.target as HTMLImageElement).src = PLACEHOLDER_IMG;
            }}
          />
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-text-primary leading-tight line-clamp-2" title={modName}>
              {modName}
            </h3>
            <div className="flex items-center gap-3 text-xs text-text-muted mt-1">
              {author && (
                <span className="flex items-center gap-1 truncate" title={author}>
                  <User size={12} />
                  {author}
                </span>
              )}
              {version && <span className="truncate" title={`v${version}`}>v{version}</span>}
              {endorsementCount != null && endorsementCount > 0 && (
                <span className="flex items-center gap-1" title={`${endorsementCount.toLocaleString()} endorsements`}>
                  <Heart size={12} />
                  {endorsementCount.toLocaleString()}
                </span>
              )}
            </div>
          </div>
          {badge && <div className="flex-shrink-0">{badge}</div>}
        </div>

        {summary && (
          <p className="text-xs text-text-muted line-clamp-2" title={summary}>{summary}</p>
        )}

        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 pt-2 border-t border-border/50">
          <div className="min-w-0">{footer ?? <div />}</div>
          <div className="flex items-center gap-1 ml-auto">
            {action}
            {overflowMenu}
          </div>
        </div>
      </div>
    </div>
  );
}
