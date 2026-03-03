import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bell, BellOff, Info, Loader2, RefreshCw, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { FileTreeView } from "@/components/ui/FileTreeView";
import { useDismissConflict, useResolveConflict, useRestoreConflict, useUninstallMod } from "@/hooks/mutations";
import { useModConflicts } from "@/hooks/queries";
import type { ArchiveEntryNode, ConflictSeverity, InstalledModOut } from "@/types/api";

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
  dismissed: boolean;
  onClose: () => void;
}

export function ConflictDetailDrawer({ gameName, modId, modName, severity, dismissed, onClose }: Props) {
  const qc = useQueryClient();
  const { data: detail, isLoading } = useModConflicts(gameName, modId);
  const resolve = useResolveConflict();
  const uninstallMod = useUninstallMod();
  const dismiss = useDismissConflict();
  const restore = useRestoreConflict();
  const [showRemoveConfirm, setShowRemoveConfirm] = useState(false);

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

  useEffect(() => {
    if (uninstallMod.isSuccess) onClose();
  }, [uninstallMod.isSuccess, onClose]);


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

  const isSuperseded = useMemo(() => {
    if (grouped.length !== 1 || detail == null) return false;
    if (detail.evidence.length !== detail.total_archive_files) return false;

    const installedMods = qc.getQueryData<InstalledModOut[]>(["installed-mods", gameName]);
    if (!installedMods) return false;

    const loser = installedMods.find((m) => m.id === modId);
    const winner = installedMods.find((m) => m.id === grouped[0][1].winnerId);
    if (!loser?.nexus_mod_id || !winner?.nexus_mod_id) return false;

    return loser.nexus_mod_id === winner.nexus_mod_id;
  }, [grouped, detail, qc, gameName, modId]);
  const winnerName = isSuperseded ? grouped[0][0] : null;

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

          {isSuperseded && winnerName && (
            <div className="flex items-start gap-2.5 rounded-lg border border-accent/30 bg-accent/5 px-3 py-2.5">
              <Info size={14} className="text-accent mt-0.5 shrink-0" />
              <div className="text-xs text-text-secondary space-y-1">
                <p className="font-medium text-text-primary">Superseded by newer version</p>
                <p>
                  All files from this mod have been replaced by &ldquo;{winnerName}&rdquo;.
                  This usually happens when a newer version is installed without removing
                  the old one first. You can safely remove this outdated entry.
                </p>
              </div>
            </div>
          )}

          {grouped.map(([groupWinnerName, { files }]) => (
            <div key={groupWinnerName}>
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle size={14} className="text-warning shrink-0" />
                <h3 className="text-sm font-medium text-text-primary truncate">
                  Overwritten by {groupWinnerName}
                </h3>
                <span className="text-xs text-text-muted shrink-0">
                  {files.length} file{files.length !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="max-h-[40vh] overflow-y-auto rounded border border-border bg-surface-0 p-3">
                <FileTreeView tree={trees.get(groupWinnerName) ?? []} showSize={false} />
              </div>
            </div>
          ))}
        </div>

        {/* Resolve actions */}
        <div className="border-t border-border px-6 py-4 flex items-center gap-3 shrink-0">
          {isSuperseded && (
            <Button
              variant="danger"
              onClick={() => setShowRemoveConfirm(true)}
              disabled={uninstallMod.isPending}
            >
              <Trash2 size={14} /> Remove old version
            </Button>
          )}
          <Button
            variant={isSuperseded ? "secondary" : undefined}
            onClick={() => resolve.mutate({ gameName, modId })}
            loading={resolve.isPending}
            disabled={!detail || detail.evidence.length === 0}
          >
            <RefreshCw size={14} /> Reinstall
          </Button>
          <div className="flex-1" />
          {dismissed ? (
            <Button
              variant="secondary"
              onClick={() => restore.mutate({ gameName, modId }, { onSuccess: onClose })}
              loading={restore.isPending}
            >
              <Bell size={14} /> Restore
            </Button>
          ) : (
            <Button
              variant="secondary"
              onClick={() => dismiss.mutate({ gameName, modId }, { onSuccess: onClose })}
              loading={dismiss.isPending}
            >
              <BellOff size={14} /> Dismiss
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
      {showRemoveConfirm && (
        <ConfirmDialog
          title="Remove old version?"
          message={`This will remove the "${modName}" entry from your installed mods. Your files are safe — they are now managed by "${winnerName}".`}
          confirmLabel="Remove"
          variant="danger"
          icon={Trash2}
          loading={uninstallMod.isPending}
          onConfirm={() =>
            uninstallMod.mutate(
              { gameName, modId },
              {
                onSuccess: () => {
                  qc.invalidateQueries({ queryKey: ["conflicts", gameName] });
                  qc.invalidateQueries({ queryKey: ["conflict-summary", gameName] });
                },
              },
            )
          }
          onCancel={() => setShowRemoveConfirm(false)}
        />
      )}
    </div>
  );
}
