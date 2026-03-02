import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  FileText,
  Pin,
  RotateCcw,
  Search,
} from "lucide-react";
import { openPath } from "@tauri-apps/plugin-opener";
import { useCallback, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { SkeletonTable } from "@/components/ui/SkeletonTable";
import { useModlistView, useArchiveConflictSummaries } from "@/hooks/queries";
import { usePreferMod, useResetAllPreferences } from "@/hooks/mutations";
import { cn } from "@/lib/utils";
import { toast } from "@/stores/toast-store";
import type { ModlistGroupEntry } from "@/types/api";

interface Props {
  gameName: string;
}

export function LoadOrderView({ gameName }: Props) {
  const { data: result, isLoading } = useModlistView(gameName);
  const { data: conflictData } = useArchiveConflictSummaries(gameName);
  const preferMod = usePreferMod();
  const resetAll = useResetAllPreferences();

  const [search, setSearch] = useState("");
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());
  const [confirmResetAll, setConfirmResetAll] = useState(false);

  const conflictCountByModId = useMemo(() => {
    const map = new Map<number, { real: number; cosmetic: number }>();
    for (const s of conflictData?.summaries ?? []) {
      if (s.installed_mod_id != null) {
        const cur = map.get(s.installed_mod_id) ?? { real: 0, cosmetic: 0 };
        map.set(s.installed_mod_id, {
          real: cur.real + s.real_count,
          cosmetic: cur.cosmetic + s.identical_count,
        });
      }
    }
    return map;
  }, [conflictData]);

  const filtered = useMemo(() => {
    if (!result) return [];
    if (!search.trim()) return result.groups;
    const q = search.toLowerCase();
    return result.groups.filter(
      (g) =>
        g.mod_name.toLowerCase().includes(q) ||
        g.archive_filenames.some((fn) => fn.toLowerCase().includes(q)),
    );
  }, [result, search]);

  const toggleExpand = useCallback((position: number) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(position)) next.delete(position);
      else next.add(position);
      return next;
    });
  }, []);

  const handleMoveUp = useCallback(
    (group: ModlistGroupEntry, aboveGroup: ModlistGroupEntry) => {
      if (group.mod_id == null || aboveGroup.mod_id == null) return;
      preferMod.mutate({
        gameName,
        data: { winner_mod_id: group.mod_id, loser_mod_ids: [aboveGroup.mod_id] },
      });
    },
    [gameName, preferMod],
  );

  const handleMoveDown = useCallback(
    (group: ModlistGroupEntry, belowGroup: ModlistGroupEntry) => {
      if (group.mod_id == null || belowGroup.mod_id == null) return;
      preferMod.mutate({
        gameName,
        data: { winner_mod_id: belowGroup.mod_id, loser_mod_ids: [group.mod_id] },
      });
    },
    [gameName, preferMod],
  );

  const handleResetAll = useCallback(() => {
    resetAll.mutate(gameName, { onSettled: () => setConfirmResetAll(false) });
  }, [gameName, resetAll]);

  const handleOpenModlist = useCallback(() => {
    if (!result) return;
    openPath(result.modlist_path).catch((e) =>
      toast.error("Could not open modlist.txt", String(e)),
    );
  }, [result]);

  if (isLoading) return <SkeletonTable columns={4} />;

  if (!result || result.groups.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-text-muted">
        <FileText size={40} className="mb-3 opacity-40" />
        <p className="text-sm">No archives found in the mod directory.</p>
        <p className="text-xs mt-1">Run a scan to detect installed mods.</p>
      </div>
    );
  }

  const fullGroups = result.groups;

  return (
    <div className="space-y-4">
      {/* Status Bar */}
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
            result.modlist_active
              ? "bg-success/10 text-success"
              : "bg-surface-2 text-text-muted",
          )}
        >
          <FileText size={12} />
          {result.modlist_active ? "modlist.txt Active" : "Default Order"}
        </span>
        {result.modlist_active && (
          <button
            onClick={handleOpenModlist}
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-text-muted hover:text-accent hover:bg-surface-2 transition-colors"
            title="Open modlist.txt in your default editor"
          >
            <ExternalLink size={11} />
            Edit
          </button>
        )}
        <span className="text-xs text-text-muted">
          {result.total_archives} archive{result.total_archives !== 1 ? "s" : ""}
        </span>
        <span
          className={cn(
            "text-xs",
            result.total_preferences > 0 ? "text-accent" : "text-text-muted",
          )}
        >
          {result.total_preferences} preference{result.total_preferences !== 1 ? "s" : ""}
        </span>
        <div className="flex-1" />
        <Button
          variant="danger"
          size="sm"
          disabled={result.total_preferences === 0 || resetAll.isPending}
          onClick={() => setConfirmResetAll(true)}
        >
          <RotateCcw size={14} />
          Reset All
        </Button>
      </div>

      {/* Search */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by mod or archive name..."
          className="w-full rounded-lg border border-border bg-surface-1 py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted/60 focus:border-accent focus:outline-none"
        />
      </div>

      {/* Group List */}
      <div className="rounded-lg border border-border overflow-hidden">
        {filtered.length === 0 ? (
          <div className="py-8 text-center text-sm text-text-muted">
            No groups match your search.
          </div>
        ) : (
          <div className="divide-y divide-border/50">
            {filtered.map((group) => {
              const isExpanded = expandedGroups.has(group.position);
              const conflicts = group.mod_id != null
                ? conflictCountByModId.get(group.mod_id)
                : undefined;
              const fullIndex = fullGroups.findIndex(
                (g) => g.position === group.position,
              );
              const isFirst = fullIndex === 0;
              const isLast = fullIndex === fullGroups.length - 1;
              const canMoveUp = !isFirst && !group.is_unmanaged && !fullGroups[fullIndex - 1]!.is_unmanaged;
              const canMoveDown = !isLast && !group.is_unmanaged && !fullGroups[fullIndex + 1]!.is_unmanaged;
              const isSingleArchive = group.archive_count === 1;

              return (
                <div key={group.position} className="bg-surface-1">
                  <div
                    className={cn(
                      "flex items-center gap-3 px-4 py-2.5",
                      group.is_unmanaged && "opacity-50",
                    )}
                  >
                    {/* Position badge */}
                    <span className="w-8 shrink-0 text-right text-xs font-mono font-bold text-accent">
                      #{group.position}
                    </span>

                    {/* Preference indicator */}
                    <span className="w-4 shrink-0" title={group.has_user_preference ? "Has user preference" : undefined}>
                      {group.has_user_preference && (
                        <Pin size={12} className="text-accent" />
                      )}
                    </span>

                    {/* Mod name + archive filename */}
                    <div
                      className="flex-1 min-w-0"
                      title={
                        group.is_unmanaged
                          ? "Not installed through the mod manager — install the mod to manage its load order"
                          : undefined
                      }
                    >
                      {group.is_unmanaged ? (
                        <span className="text-sm font-mono text-text-muted/50 truncate block">
                          {group.archive_filenames[0]}
                        </span>
                      ) : (
                        <>
                          <span className="text-sm font-medium text-text-primary truncate block">
                            {group.mod_name}
                          </span>
                          {isSingleArchive && (
                            <span className="text-xs font-mono text-text-muted truncate block">
                              {group.archive_filenames[0]}
                            </span>
                          )}
                        </>
                      )}
                    </div>

                    {/* Archive count chip (only for multi-archive groups) */}
                    {!isSingleArchive && (
                      <button
                        onClick={() => toggleExpand(group.position)}
                        className="shrink-0 rounded px-2 py-0.5 text-xs text-text-muted hover:bg-surface-2 transition-colors"
                        title="Toggle archive list"
                      >
                        {group.archive_count} archives
                      </button>
                    )}

                    {/* Conflict badge */}
                    {conflicts && conflicts.real > 0 && (
                      <span
                        className="shrink-0 rounded-full bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning"
                        title={`${conflicts.real} real, ${conflicts.cosmetic} identical`}
                      >
                        {conflicts.real} conflict{conflicts.real !== 1 ? "s" : ""}
                      </span>
                    )}

                    {/* Move buttons */}
                    <div className="flex shrink-0 gap-0.5">
                      <button
                        onClick={() =>
                          canMoveUp && handleMoveUp(group, fullGroups[fullIndex - 1]!)
                        }
                        disabled={!canMoveUp || preferMod.isPending}
                        className={cn(
                          "rounded p-1 transition-colors",
                          canMoveUp && !preferMod.isPending
                            ? "text-text-muted hover:text-text-primary hover:bg-surface-2"
                            : "text-text-muted/20 cursor-not-allowed",
                        )}
                        title={
                          group.is_unmanaged
                            ? "Cannot reorder unmanaged archives"
                            : "Move up"
                        }
                      >
                        <ChevronUp size={16} />
                      </button>
                      <button
                        onClick={() =>
                          canMoveDown && handleMoveDown(group, fullGroups[fullIndex + 1]!)
                        }
                        disabled={!canMoveDown || preferMod.isPending}
                        className={cn(
                          "rounded p-1 transition-colors",
                          canMoveDown && !preferMod.isPending
                            ? "text-text-muted hover:text-text-primary hover:bg-surface-2"
                            : "text-text-muted/20 cursor-not-allowed",
                        )}
                        title={
                          group.is_unmanaged
                            ? "Cannot reorder unmanaged archives"
                            : "Move down"
                        }
                      >
                        <ChevronDown size={16} />
                      </button>
                    </div>
                  </div>

                  {/* Expanded archive list */}
                  {isExpanded && !isSingleArchive && (
                    <div className="border-t border-border/30 bg-surface-0 px-4 py-2">
                      {group.archive_filenames.map((fn, i) => (
                        <div
                          key={fn}
                          className="flex items-center gap-2 py-0.5 text-xs font-mono text-text-muted"
                        >
                          <span className="text-border">
                            {i === group.archive_filenames.length - 1 ? "\u2514" : "\u251C"}
                          </span>
                          {fn}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Reset All Confirmation */}
      {confirmResetAll && (
        <ConfirmDialog
          title="Reset All Preferences"
          message={`This will remove all ${result.total_preferences} load order preference${result.total_preferences !== 1 ? "s" : ""} and revert to default ASCII filename order.`}
          confirmLabel="Reset All"
          variant="danger"
          icon={RotateCcw}
          loading={resetAll.isPending}
          onConfirm={handleResetAll}
          onCancel={() => setConfirmResetAll(false)}
        />
      )}
    </div>
  );
}
