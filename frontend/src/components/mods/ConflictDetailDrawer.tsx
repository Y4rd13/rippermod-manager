import { AlertTriangle, Loader2, RefreshCw, X } from "lucide-react";
import { useEffect, useMemo } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useResolveConflict } from "@/hooks/mutations";
import { useModConflicts } from "@/hooks/queries";
import type { ConflictSeverity } from "@/types/api";

interface Props {
  gameName: string;
  modId: number;
  modName: string;
  severity: ConflictSeverity;
  onClose: () => void;
}

export function ConflictDetailDrawer({ gameName, modId, modName, severity, onClose }: Props) {
  const { data: detail, isLoading } = useModConflicts(gameName, modId);
  const resolve = useResolveConflict();

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const grouped = useMemo(() => {
    if (!detail?.evidence.length) return [];
    const map = new Map<string, { winnerId: number; files: string[] }>();
    for (const e of detail.evidence) {
      const existing = map.get(e.winner_mod_name);
      if (existing) {
        existing.files.push(e.file_path);
      } else {
        map.set(e.winner_mod_name, { winnerId: e.winner_mod_id, files: [e.file_path] });
      }
    }
    return [...map.entries()].sort((a, b) => b[1].files.length - a[1].files.length);
  }, [detail]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      <div className="relative w-full max-w-lg bg-surface-0 border-l border-border flex flex-col animate-slide-in-right">
        {/* Header */}
        <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-text-primary truncate">{modName}</h2>
            <div className="flex items-center gap-2 mt-1">
              <Badge variant={severity === "critical" ? "danger" : "warning"}>
                <AlertTriangle size={10} className="mr-0.5" />
                {severity}
              </Badge>
              {detail && (
                <span className="text-xs text-text-muted">
                  {detail.evidence.length} conflicting file{detail.evidence.length !== 1 ? "s" : ""} / {detail.total_archive_files} total
                </span>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-lg p-1.5 text-text-muted hover:text-text-primary hover:bg-surface-2 transition-colors"
            aria-label="Close drawer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Evidence list */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={24} className="animate-spin text-text-muted" />
            </div>
          )}

          {!isLoading && grouped.length === 0 && (
            <p className="text-sm text-text-muted text-center py-8">
              No file conflicts found for this mod.
            </p>
          )}

          {grouped.map(([winnerName, { files }]) => (
            <div key={winnerName}>
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle size={14} className="text-warning shrink-0" />
                <h3 className="text-sm font-medium text-text-primary truncate">
                  Overwritten by {winnerName}
                </h3>
                <span className="text-xs text-text-muted shrink-0">
                  {files.length} file{files.length !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="rounded-lg border border-border bg-surface-1 p-3 max-h-48 overflow-y-auto">
                {files.map((fp) => (
                  <p key={fp} className="text-xs font-mono text-text-secondary leading-relaxed truncate">
                    {fp}
                  </p>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Resolve actions */}
        <div className="border-t border-border px-5 py-4 flex items-center gap-3">
          <Button
            onClick={() => resolve.mutate({ gameName, modId })}
            loading={resolve.isPending}
            disabled={!detail || detail.evidence.length === 0}
          >
            <RefreshCw size={14} /> Reinstall
          </Button>
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
