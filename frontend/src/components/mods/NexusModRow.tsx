import { Heart, User } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const PLACEHOLDER_IMG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80' fill='%231a1a2e'%3E%3Crect width='80' height='80'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%23555' font-size='9'%3ENo Image%3C/text%3E%3C/svg%3E";

const SUMMARY_MAX_CHARS = 90;
function clampSummary(text?: string): string | undefined {
  if (!text) return text;
  return text.length > SUMMARY_MAX_CHARS ? `${text.slice(0, SUMMARY_MAX_CHARS - 1)}…` : text;
}

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

export function NexusModRow({
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
    <tr
      className={cn(
        "border-b border-border/50 transition-colors",
        onClick && "cursor-pointer hover:bg-surface-1/50",
      )}
      onClick={onClick}
      onContextMenu={onContextMenu}
    >
      <td className="py-2 pr-3 w-[68px]">
        <img
          src={pictureUrl || PLACEHOLDER_IMG}
          alt={modName}
          loading="lazy"
          className="h-14 w-14 rounded-md object-cover bg-surface-2"
          onError={(e) => {
            (e.target as HTMLImageElement).src = PLACEHOLDER_IMG;
          }}
        />
      </td>
      <td className="py-2 pr-3 min-w-0 overflow-hidden">
        <div className="flex flex-col gap-0.5 min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <h3
              className="text-sm font-medium text-text-primary truncate"
              title={modName}
            >
              {modName}
            </h3>
            {badge && <div className="flex items-center gap-1 shrink-0">{badge}</div>}
          </div>
          {summary && (
            <p className="text-xs text-text-muted truncate" title={summary}>
              {clampSummary(summary)}
            </p>
          )}
        </div>
      </td>
      <td className="py-2 pr-3 text-xs text-text-muted whitespace-nowrap max-w-[140px] truncate">
        {author && (
          <span className="flex items-center gap-1" title={author}>
            <User size={11} />
            {author}
          </span>
        )}
      </td>
      <td className="py-2 pr-3 text-xs text-text-muted whitespace-nowrap">
        {version && <span title={`v${version}`}>v{version}</span>}
      </td>
      <td className="py-2 pr-3 text-xs text-text-muted whitespace-nowrap">
        {endorsementCount != null && endorsementCount > 0 && (
          <span
            className="flex items-center gap-1"
            title={`${endorsementCount.toLocaleString()} endorsements on Nexus`}
          >
            <Heart size={11} />
            {endorsementCount.toLocaleString()}
          </span>
        )}
      </td>
      <td className="py-2 pr-3 text-xs text-text-muted overflow-hidden">
        <div className="flex flex-wrap items-center gap-1">{footer}</div>
      </td>
      <td className="py-2 pl-2 whitespace-nowrap text-right">
        <div className="inline-flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          {action}
          {overflowMenu}
        </div>
      </td>
    </tr>
  );
}
