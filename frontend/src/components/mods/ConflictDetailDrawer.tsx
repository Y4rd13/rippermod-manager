import { AlertTriangle, Loader2, RefreshCw, X } from "lucide-react";
import { useEffect, useMemo } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { FileTreeView } from "@/components/ui/FileTreeView";
import { useResolveConflict } from "@/hooks/mutations";
import { useModConflicts } from "@/hooks/queries";
import type { ArchiveEntryNode, ConflictSeverity } from "@/types/api";

function pathsToTree(paths: string[]): ArchiveEntryNode[] {
  interface TreeMap {
    children: Map<string, TreeMap>;
    isDir: boolean;
  }

  const root: TreeMap = { children: new Map(), isDir: true };

  for (const p of paths) {
    const parts = p.split("/").filter(Boolean);
    let current = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      if (!current.children.has(part)) {
        current.children.set(part, {
          children: new Map(),
          isDir: i < parts.length - 1,
        });
      } else if (i < parts.length - 1) {
        current.children.get(part)!.isDir = true;
      }
      current = current.children.get(part)!;
    }
  }

  function toNodes(map: Map<string, TreeMap>): ArchiveEntryNode[] {
    const nodes: ArchiveEntryNode[] = [];
    for (const [name, entry] of map) {
      nodes.push({
        name,
        is_dir: entry.isDir,
        size: 0,
        children: entry.isDir ? toNodes(entry.children) : [],
      });
    }
    nodes.sort((a, b) => {
      if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    return nodes;
  }

  return toNodes(root.children);
}

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

  useEffect(() => {
    if (resolve.isSuccess) onClose();
  }, [resolve.isSuccess, onClose]);

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

  const trees = useMemo(
    () => new Map(grouped.map(([name, { files }]) => [name, pathsToTree(files)])),
    [grouped],
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="conflict-detail-title"
        className="w-full max-w-2xl rounded-xl border border-border bg-surface-1 flex flex-col max-h-[85vh] animate-modal-in"
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-3 border-b border-border px-6 py-4 shrink-0">
          <div className="min-w-0">
            <h2 id="conflict-detail-title" className="text-base font-semibold text-text-primary truncate">{modName}</h2>
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
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Evidence list with inline trees */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
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
              <div className="max-h-[40vh] overflow-y-auto rounded border border-border bg-surface-0 p-3">
                <FileTreeView tree={trees.get(winnerName) ?? []} showSize={false} />
              </div>
            </div>
          ))}
        </div>

        {/* Resolve actions */}
        <div className="border-t border-border px-6 py-4 flex items-center gap-3 shrink-0">
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
