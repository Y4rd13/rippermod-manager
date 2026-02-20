import { ExternalLink, Heart, User } from "lucide-react";
import type { ReactNode } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";

const PLACEHOLDER_IMG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='320' height='180' fill='%231a1a2e'%3E%3Crect width='320' height='180'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%23555' font-size='14'%3ENo Image%3C/text%3E%3C/svg%3E";

interface Props {
  modName: string;
  summary?: string;
  author?: string;
  version?: string;
  endorsementCount?: number;
  pictureUrl?: string;
  nexusUrl?: string;
  action?: ReactNode;
  footer?: ReactNode;
}

export function NexusModCard({
  modName,
  summary,
  author,
  version,
  endorsementCount,
  pictureUrl,
  nexusUrl,
  action,
  footer,
}: Props) {
  return (
    <div className="rounded-xl border border-border bg-surface-1 overflow-hidden flex flex-col">
      <img
        src={pictureUrl || PLACEHOLDER_IMG}
        alt={modName}
        loading="lazy"
        className="w-full h-40 object-cover bg-surface-2"
        onError={(e) => {
          (e.target as HTMLImageElement).src = PLACEHOLDER_IMG;
        }}
      />

      <div className="p-4 flex flex-col flex-1 gap-2">
        <div className="flex items-start gap-2">
          <h3 className="text-sm font-semibold text-text-primary leading-tight flex-1 line-clamp-2">
            {modName}
          </h3>
          {nexusUrl && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                openUrl(nexusUrl).catch(() => {});
              }}
              className="text-accent hover:text-accent/80 shrink-0 mt-0.5"
              title="Open on Nexus Mods"
            >
              <ExternalLink size={14} />
            </button>
          )}
        </div>

        {summary && (
          <p className="text-xs text-text-muted line-clamp-2">{summary}</p>
        )}

        <div className="flex items-center gap-3 text-xs text-text-muted mt-auto pt-1">
          {author && (
            <span className="flex items-center gap-1 truncate">
              <User size={12} />
              {author}
            </span>
          )}
          {version && <span className="truncate">v{version}</span>}
          {endorsementCount != null && endorsementCount > 0 && (
            <span className="flex items-center gap-1">
              <Heart size={12} />
              {endorsementCount.toLocaleString()}
            </span>
          )}
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-border/50">
          {footer ?? <div />}
          {action ?? <div />}
        </div>
      </div>
    </div>
  );
}
