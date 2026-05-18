import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  FileText,
  GripVertical,
  Pin,
  RotateCcw,
  Search,
  Sparkles,
} from "lucide-react";
import { openPath } from "@tauri-apps/plugin-opener";
import { useCallback, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { SkeletonTable } from "@/components/ui/SkeletonTable";
import { useModlistView, useArchiveConflictSummaries } from "@/hooks/queries";
import {
  useAutoSortApply,
  useAutoSortPreview,
  usePreferencesBatch,
  useResetAllPreferences,
} from "@/hooks/mutations";
import { cn } from "@/lib/utils";
import { toast } from "@/stores/toast-store";
import type {
  AutoSortPreview as AutoSortPreviewT,
  ModlistGroupEntry,
  PreferencePair,
} from "@/types/api";

interface Props {
  gameName: string;
}

type ConflictCount = { real: number; cosmetic: number } | undefined;

interface RowProps {
  group: ModlistGroupEntry;
  canDrag: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  isExpanded: boolean;
  isPending: boolean;
  conflicts: ConflictCount;
  onToggleExpand: (position: number) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

function SortableRow({
  group,
  canDrag,
  canMoveUp,
  canMoveDown,
  isExpanded,
  isPending,
  conflicts,
  onToggleExpand,
  onMoveUp,
  onMoveDown,
}: RowProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: rowId(group),
    disabled: !canDrag,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 10 : undefined,
  };

  const isSingleArchive = group.archive_count === 1;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "bg-surface-1",
        isDragging && "shadow-lg ring-1 ring-accent/40",
      )}
    >
      <div
        className={cn(
          "flex items-center gap-3 px-4 py-2.5",
          group.is_unmanaged && "opacity-50",
        )}
      >
        {/* Drag handle */}
        <button
          type="button"
          className={cn(
            "shrink-0 rounded p-1 -ml-1 transition-colors",
            canDrag
              ? "text-text-muted hover:text-text-primary hover:bg-surface-2 cursor-grab active:cursor-grabbing"
              : "text-text-muted/20 cursor-not-allowed",
          )}
          aria-label={canDrag ? "Drag to reorder" : "Cannot reorder unmanaged"}
          title={
            canDrag
              ? "Drag to reorder"
              : "Unmanaged archives cannot be reordered"
          }
          {...(canDrag ? attributes : {})}
          {...(canDrag ? listeners : {})}
        >
          <GripVertical size={14} />
        </button>

        {/* Position badge */}
        <span className="w-8 shrink-0 text-right text-xs font-mono font-bold text-accent">
          #{group.position}
        </span>

        {/* Preference indicator */}
        <span
          className="w-4 shrink-0"
          title={group.has_user_preference ? "Has user preference" : undefined}
        >
          {group.has_user_preference && <Pin size={12} className="text-accent" />}
        </span>

        {/* Mod name + archive filename */}
        <div
          className="flex-1 min-w-0"
          title={
            group.is_unmanaged
              ? "Not installed through the mod manager - install the mod to manage its load order"
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
            onClick={() => onToggleExpand(group.position)}
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

        {/* Move buttons (fallback) */}
        <div className="flex shrink-0 gap-0.5">
          <button
            onClick={() => canMoveUp && onMoveUp()}
            disabled={!canMoveUp || isPending}
            className={cn(
              "rounded p-1 transition-colors",
              canMoveUp && !isPending
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
            onClick={() => canMoveDown && onMoveDown()}
            disabled={!canMoveDown || isPending}
            className={cn(
              "rounded p-1 transition-colors",
              canMoveDown && !isPending
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
                {i === group.archive_filenames.length - 1 ? "└" : "├"}
              </span>
              {fn}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function rowId(group: ModlistGroupEntry): string {
  return group.mod_id != null ? `mod-${group.mod_id}` : `un-${group.position}`;
}

/**
 * Compute the minimum pairwise diff to take the current ordered group list
 * from `prev` to `next`. Only managed mods (mod_id != null) participate in
 * preferences - unmanaged archives cannot be reordered.
 */
function computeReorderDiff(
  prev: ModlistGroupEntry[],
  next: ModlistGroupEntry[],
): { add: PreferencePair[]; remove: PreferencePair[] } {
  const prevPos = new Map<number, number>();
  prev.forEach((g, i) => {
    if (g.mod_id != null) prevPos.set(g.mod_id, i);
  });
  const nextPos = new Map<number, number>();
  next.forEach((g, i) => {
    if (g.mod_id != null) nextPos.set(g.mod_id, i);
  });

  const add: PreferencePair[] = [];
  const remove: PreferencePair[] = [];

  const managedIds = Array.from(nextPos.keys());
  for (const a of managedIds) {
    for (const b of managedIds) {
      if (a === b) continue;
      const prevA = prevPos.get(a);
      const prevB = prevPos.get(b);
      const nextA = nextPos.get(a)!;
      const nextB = nextPos.get(b)!;
      if (prevA == null || prevB == null) continue;
      const wasBefore = prevA < prevB;
      const isBefore = nextA < nextB;
      if (wasBefore === isBefore) continue;
      // Only emit each unordered pair once - emit when (a, b) flipped from
      // a-before-b to a-after-b. The opposite direction is handled when we
      // iterate (b, a).
      if (!isBefore) {
        // a is now AFTER b - so we want b > a
        add.push({ winner_mod_id: b, loser_mod_id: a });
        remove.push({ winner_mod_id: a, loser_mod_id: b });
      }
    }
  }
  return { add, remove };
}

export function LoadOrderView({ gameName }: Props) {
  const { data: result, isLoading } = useModlistView(gameName);
  const { data: conflictData } = useArchiveConflictSummaries(gameName);
  const preferencesBatch = usePreferencesBatch();
  const resetAll = useResetAllPreferences();
  const autoSortPreviewMut = useAutoSortPreview();
  const autoSortApply = useAutoSortApply();

  const [search, setSearch] = useState("");
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());
  const [confirmResetAll, setConfirmResetAll] = useState(false);
  const [autoSortPlan, setAutoSortPlan] = useState<AutoSortPreviewT | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

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

  const submitPair = useCallback(
    (winner: ModlistGroupEntry, loser: ModlistGroupEntry) => {
      if (winner.mod_id == null || loser.mod_id == null) return;
      preferencesBatch.mutate({
        gameName,
        data: {
          add: [{ winner_mod_id: winner.mod_id, loser_mod_id: loser.mod_id }],
          remove: [{ winner_mod_id: loser.mod_id, loser_mod_id: winner.mod_id }],
        },
      });
    },
    [gameName, preferencesBatch],
  );

  const handleMoveUp = useCallback(
    (group: ModlistGroupEntry, aboveGroup: ModlistGroupEntry) =>
      submitPair(group, aboveGroup),
    [submitPair],
  );

  const handleMoveDown = useCallback(
    (group: ModlistGroupEntry, belowGroup: ModlistGroupEntry) =>
      submitPair(belowGroup, group),
    [submitPair],
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || !result) return;
      const activeId = String(active.id);
      const overId = String(over.id);
      if (activeId === overId) return;

      const allGroups = result.groups;
      const fromIdx = allGroups.findIndex((g) => rowId(g) === activeId);
      const toIdx = allGroups.findIndex((g) => rowId(g) === overId);
      if (fromIdx < 0 || toIdx < 0) return;

      const movedGroup = allGroups[fromIdx]!;
      const targetGroup = allGroups[toIdx]!;
      if (movedGroup.is_unmanaged || targetGroup.is_unmanaged) {
        toast.warning("Cannot reorder unmanaged archives");
        return;
      }

      const next = arrayMove(allGroups, fromIdx, toIdx);
      const diff = computeReorderDiff(allGroups, next);
      if (diff.add.length === 0 && diff.remove.length === 0) return;
      preferencesBatch.mutate({ gameName, data: diff });
    },
    [result, gameName, preferencesBatch],
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

  const handleAutoSortClick = useCallback(() => {
    autoSortPreviewMut.mutate(gameName, {
      onSuccess: (preview) => setAutoSortPlan(preview),
    });
  }, [gameName, autoSortPreviewMut]);

  const handleAutoSortApply = useCallback(() => {
    autoSortApply.mutate(gameName, {
      onSettled: () => setAutoSortPlan(null),
    });
  }, [gameName, autoSortApply]);

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
  const sortableIds = fullGroups.map(rowId);

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
          variant="primary"
          size="sm"
          disabled={autoSortPreviewMut.isPending || autoSortApply.isPending}
          loading={autoSortPreviewMut.isPending}
          onClick={handleAutoSortClick}
          title="Suggest a load order based on conflicts (smaller mod = wins)"
        >
          <Sparkles size={14} />
          Auto-sort
        </Button>
        <Button
          variant="danger"
          size="sm"
          disabled={result.total_preferences === 0 || resetAll.isPending}
          onClick={() => setConfirmResetAll(true)}
        >
          <RotateCcw size={14} />
          Reset to Default Order
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
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
              <div className="divide-y divide-border/50">
                {filtered.map((group) => {
                  const isExpanded = expandedGroups.has(group.position);
                  const conflicts =
                    group.mod_id != null
                      ? conflictCountByModId.get(group.mod_id)
                      : undefined;
                  const fullIndex = fullGroups.findIndex(
                    (g) => g.position === group.position,
                  );
                  const isFirst = fullIndex === 0;
                  const isLast = fullIndex === fullGroups.length - 1;
                  const canMoveUp =
                    !isFirst &&
                    !group.is_unmanaged &&
                    !fullGroups[fullIndex - 1]!.is_unmanaged;
                  const canMoveDown =
                    !isLast &&
                    !group.is_unmanaged &&
                    !fullGroups[fullIndex + 1]!.is_unmanaged;
                  const canDrag =
                    !group.is_unmanaged && !preferencesBatch.isPending;

                  return (
                    <SortableRow
                      key={rowId(group)}
                      group={group}
                      canDrag={canDrag}
                      canMoveUp={canMoveUp}
                      canMoveDown={canMoveDown}
                      isExpanded={isExpanded}
                      isPending={preferencesBatch.isPending}
                      conflicts={conflicts}
                      onToggleExpand={toggleExpand}
                      onMoveUp={() =>
                        canMoveUp && handleMoveUp(group, fullGroups[fullIndex - 1]!)
                      }
                      onMoveDown={() =>
                        canMoveDown && handleMoveDown(group, fullGroups[fullIndex + 1]!)
                      }
                    />
                  );
                })}
              </div>
            </SortableContext>
          </DndContext>
        )}
      </div>

      {/* Reset All Confirmation */}
      {confirmResetAll && (
        <ConfirmDialog
          title="Reset to Default Order"
          message={`This will remove all ${result.total_preferences} load order preference${result.total_preferences !== 1 ? "s" : ""} and revert to default ASCII filename order.`}
          confirmLabel="Reset"
          variant="danger"
          icon={RotateCcw}
          loading={resetAll.isPending}
          onConfirm={handleResetAll}
          onCancel={() => setConfirmResetAll(false)}
        />
      )}

      {/* Auto-sort Preview Dialog */}
      {autoSortPlan && (
        <AutoSortPreviewDialog
          preview={autoSortPlan}
          loading={autoSortApply.isPending}
          onApply={handleAutoSortApply}
          onCancel={() => setAutoSortPlan(null)}
        />
      )}
    </div>
  );
}

interface AutoSortPreviewDialogProps {
  preview: AutoSortPreviewT;
  loading: boolean;
  onApply: () => void;
  onCancel: () => void;
}

function AutoSortPreviewDialog({
  preview,
  loading,
  onApply,
  onCancel,
}: AutoSortPreviewDialogProps) {
  const hasChanges =
    preview.proposed_add.length > 0 || preview.proposed_remove.length > 0;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onClick={() => !loading && onCancel()}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-lg rounded-xl border border-border bg-surface-1 p-6 max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center gap-2 text-accent">
          <Sparkles size={20} />
          <h3 className="text-lg font-semibold text-text-primary">
            Auto-sort Preview
          </h3>
        </div>

        <p className="mb-4 text-sm text-text-secondary">{preview.rationale}</p>

        {hasChanges ? (
          <div className="mb-6 space-y-3">
            <div className="text-xs text-text-muted">
              {preview.proposed_add.length} preference{preview.proposed_add.length !== 1 ? "s" : ""}{" "}
              to add
              {preview.proposed_remove.length > 0 &&
                `, ${preview.proposed_remove.length} to remove`}
              .
            </div>
            {preview.affected_mods.length > 0 && (
              <div className="rounded border border-border bg-surface-0 p-3">
                <div className="mb-2 text-xs font-medium text-text-secondary">
                  Affected mods (sorted by file count, smaller = wins):
                </div>
                <ul className="space-y-1 text-xs font-mono">
                  {preview.affected_mods.map((m) => (
                    <li
                      key={m.mod_id}
                      className="flex items-center justify-between gap-2"
                    >
                      <span className="truncate text-text-primary">{m.mod_name}</span>
                      <span className="shrink-0 text-text-muted">
                        {m.file_count} file{m.file_count !== 1 ? "s" : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="mb-6 rounded border border-border bg-surface-0 p-3 text-xs text-text-muted">
            Nothing to change.
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" disabled={loading} onClick={onCancel}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!hasChanges}
            loading={loading}
            onClick={onApply}
          >
            Apply
          </Button>
        </div>
      </div>
    </div>
  );
}
