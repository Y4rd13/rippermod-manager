import {
  ArrowUp,
  ChevronDown,
  ChevronRight,
  Clock,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  Heart,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useAbstainMod, useEndorseMod, useTrackMod, useUntrackMod } from "@/hooks/mutations";
import { useModDetail } from "@/hooks/queries";
import { bbcodeToHtml } from "@/lib/bbcode";
import { formatBytes, formatCount, isoToEpoch, timeAgo } from "@/lib/format";
import type { ModUpdate } from "@/types/api";
import type { ReactNode } from "react";

const FILE_CATEGORY_LABELS: Record<number, string> = {
  1: "Main",
  2: "Update",
  3: "Optional",
  4: "Old",
  5: "Miscellaneous",
  6: "Deleted",
  7: "Archived",
};

type ModalTab = "about" | "changelog" | "files";

const PLACEHOLDER_BANNER =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='768' height='160' fill='%231a1a25'%3E%3Crect width='768' height='160'/%3E%3C/svg%3E";

interface Props {
  gameDomain: string;
  gameName?: string;
  modId: number;
  update?: ModUpdate;
  action?: ReactNode;
  onClose: () => void;
}

export function ModDetailModal({ gameDomain, gameName, modId, update, action, onClose }: Props) {
  const { data: detail, isLoading } = useModDetail(gameDomain, modId);
  const endorseMod = useEndorseMod();
  const abstainMod = useAbstainMod();
  const trackMod = useTrackMod();
  const untrackMod = useUntrackMod();
  const [activeTab, setActiveTab] = useState<ModalTab>("about");
  const [expandedVersions, setExpandedVersions] = useState<Set<string>>(new Set());

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [handleKeyDown]);

  const sortedChangelogVersions = detail?.changelogs
    ? Object.keys(detail.changelogs).sort((a, b) =>
        b.localeCompare(a, undefined, { numeric: true }),
      )
    : [];

  // Track whether user has interacted with the changelog
  const [userToggledChangelog, setUserToggledChangelog] = useState(false);

  const isVersionExpanded = (ver: string) => {
    if (!userToggledChangelog) return ver === sortedChangelogVersions[0];
    return expandedVersions.has(ver);
  };

  const toggleVersion = (version: string) => {
    setUserToggledChangelog(true);
    setExpandedVersions((prev) => {
      const next = new Set(prev);
      if (next.has(version)) next.delete(version);
      else next.add(version);
      return next;
    });
  };

  const visibleFiles = detail?.files
    ?.filter((f) => f.category_id !== 7)
    .sort((a, b) => (b.uploaded_timestamp ?? 0) - (a.uploaded_timestamp ?? 0));

  const tabs: { key: ModalTab; label: string; show: boolean }[] = [
    { key: "about", label: "About", show: true },
    { key: "changelog", label: "Changelog", show: sortedChangelogVersions.length > 0 },
    { key: "files", label: `Files${visibleFiles ? ` (${visibleFiles.length})` : ""}`, show: (visibleFiles?.length ?? 0) > 0 },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-2xl max-h-[90vh] rounded-xl border border-border bg-surface-0 overflow-hidden flex flex-col animate-modal-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Loading skeleton */}
        {isLoading && (
          <div className="animate-pulse">
            <div className="h-40 bg-surface-2" />
            <div className="flex items-center gap-4 px-5 py-3 border-b border-border">
              <div className="h-3 w-20 bg-surface-2 rounded" />
              <div className="h-3 w-12 bg-surface-2 rounded" />
              <div className="h-3 w-16 bg-surface-2 rounded" />
            </div>
            <div className="px-5 py-5 space-y-3">
              <div className="h-4 w-3/4 bg-surface-2 rounded" />
              <div className="h-3 w-full bg-surface-2 rounded" />
              <div className="h-3 w-full bg-surface-2 rounded" />
              <div className="h-3 w-2/3 bg-surface-2 rounded" />
            </div>
          </div>
        )}

        {detail && (
          <>
            {/* Header — sticky */}
            <div className="flex-shrink-0">
              {/* Banner image with overlay */}
              <div className="relative h-40 overflow-hidden">
                <img
                  src={detail.picture_url || PLACEHOLDER_BANNER}
                  alt=""
                  className="w-full h-full object-cover bg-surface-2"
                  onError={(e) => {
                    (e.target as HTMLImageElement).src = PLACEHOLDER_BANNER;
                  }}
                />
                <div className="absolute inset-0 bg-gradient-to-t from-surface-0 via-surface-0/40 to-transparent" />
                <button
                  className="absolute top-3 right-3 z-10 rounded-lg p-1.5 bg-surface-0/60 text-text-muted hover:text-text-primary hover:bg-surface-0/80 transition-colors backdrop-blur-sm"
                  onClick={onClose}
                >
                  <X size={18} />
                </button>
                <h2 className="absolute bottom-3 left-5 right-14 text-lg font-bold text-text-primary leading-tight drop-shadow-lg">
                  {detail.name}
                </h2>
              </div>

              {/* Meta row */}
              <div className="flex items-center gap-4 px-5 py-3 text-xs text-text-muted border-b border-border">
                <span className="text-text-secondary">by {detail.author}</span>
                <span>v{detail.version}</span>
                {update && (
                  <Badge variant="warning"><ArrowUp size={10} className="mr-0.5" />v{update.nexus_version} available</Badge>
                )}
                <span className="flex items-center gap-1">
                  <Download size={12} />
                  {formatCount(detail.mod_downloads)}
                </span>
                <span className="flex items-center gap-1">
                  <Heart size={12} />
                  {formatCount(detail.endorsement_count)}
                </span>
                {detail.updated_at && (
                  <span className="flex items-center gap-1">
                    <Clock size={12} />
                    {timeAgo(isoToEpoch(detail.updated_at))}
                  </span>
                )}
              </div>

              {/* Tab bar */}
              <div className="flex gap-1 px-5 border-b border-border">
                {tabs.filter((t) => t.show).map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setActiveTab(t.key)}
                    className={`px-3 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
                      activeTab === t.key
                        ? "border-accent text-accent"
                        : "border-transparent text-text-muted hover:text-text-secondary"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Scrollable content */}
            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {/* About tab */}
              {activeTab === "about" && (
                <>
                  {detail.summary && (
                    <p className="text-sm text-text-secondary italic">{detail.summary}</p>
                  )}
                  {detail.description && (
                    <div
                      className="text-sm text-text-secondary leading-relaxed
                        [&_strong]:text-text-primary [&_strong]:font-semibold
                        [&_em]:italic
                        [&_a]:text-accent [&_a]:underline [&_a:hover]:text-accent-hover
                        [&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:italic [&_blockquote]:text-text-muted [&_blockquote]:my-2
                        [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-0.5 [&_ul]:my-2
                        [&_h3]:text-text-primary [&_h3]:font-semibold [&_h3]:text-base [&_h3]:mt-4 [&_h3]:mb-1
                        [&_img]:max-w-full [&_img]:rounded [&_img]:my-2
                        [&_pre]:bg-surface-2 [&_pre]:rounded [&_pre]:p-2 [&_pre]:text-xs [&_pre]:overflow-x-auto [&_pre]:my-2
                        [&_hr]:border-border [&_hr]:my-3"
                      dangerouslySetInnerHTML={{ __html: bbcodeToHtml(detail.description) }}
                    />
                  )}
                </>
              )}

              {/* Changelog tab */}
              {activeTab === "changelog" && (
                <div className="space-y-1">
                  {sortedChangelogVersions.map((ver) => {
                    const expanded = isVersionExpanded(ver);
                    const entries = detail.changelogs[ver] ?? [];
                    return (
                      <div key={ver}>
                        <button
                          className="flex items-center gap-1 text-sm text-text-secondary hover:text-text-primary w-full text-left py-1.5"
                          onClick={() => toggleVersion(ver)}
                        >
                          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          <span className="font-medium">v{ver}</span>
                          <span className="text-text-muted text-xs ml-1">
                            ({entries.length} change{entries.length !== 1 ? "s" : ""})
                          </span>
                        </button>
                        {expanded && (
                          <ul className="ml-6 text-xs text-text-muted list-disc space-y-0.5 pb-2">
                            {entries.map((entry, i) => (
                              <li key={i}>{entry}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Files tab */}
              {activeTab === "files" && visibleFiles && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {visibleFiles.map((f) => (
                    <div
                      key={f.file_id}
                      className="rounded-lg border border-border bg-surface-1 p-3"
                    >
                      <p className="text-sm text-text-primary font-medium truncate" title={f.file_name}>
                        {f.file_name}
                      </p>
                      <div className="flex items-center gap-3 text-xs text-text-muted mt-1 flex-wrap">
                        {f.version && <span>v{f.version}</span>}
                        {f.category_id != null && (
                          <Badge variant="neutral">
                            {FILE_CATEGORY_LABELS[f.category_id] ?? `Cat ${f.category_id}`}
                          </Badge>
                        )}
                        {f.file_size > 0 && <span>{formatBytes(f.file_size)}</span>}
                        {f.uploaded_timestamp && (
                          <span>{timeAgo(f.uploaded_timestamp)}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Footer — sticky */}
            <div className="flex-shrink-0 border-t border-border px-5 py-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => openUrl(detail.nexus_url).catch(() => {})}
                >
                  <ExternalLink size={14} />
                  View on Nexus
                </Button>
                {gameName && (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={endorseMod.isPending || abstainMod.isPending}
                      onClick={() => {
                        if (detail.is_endorsed) abstainMod.mutate({ gameName, modId });
                        else endorseMod.mutate({ gameName, modId });
                      }}
                      className={detail.is_endorsed ? "text-danger" : ""}
                    >
                      <Heart size={14} fill={detail.is_endorsed ? "currentColor" : "none"} />
                      {detail.is_endorsed ? "Endorsed" : "Endorse"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={trackMod.isPending || untrackMod.isPending}
                      onClick={() => {
                        if (detail.is_tracked) untrackMod.mutate({ gameName, modId });
                        else trackMod.mutate({ gameName, modId });
                      }}
                      className={detail.is_tracked ? "text-accent" : ""}
                    >
                      {detail.is_tracked ? <EyeOff size={14} /> : <Eye size={14} />}
                      {detail.is_tracked ? "Tracked" : "Track"}
                    </Button>
                  </>
                )}
              </div>
              {action && <div className="flex items-center gap-2">{action}</div>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
