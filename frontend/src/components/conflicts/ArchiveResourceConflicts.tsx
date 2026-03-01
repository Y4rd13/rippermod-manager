import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Crown,
  List,
  Power,
  RefreshCw,
  ShieldAlert,
  Shuffle,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { SearchInput } from "@/components/ui/SearchInput";
import { SkeletonTable } from "@/components/ui/SkeletonTable";
import { VirtualTable } from "@/components/ui/VirtualTable";
import { ResourceDetailsPanel } from "@/components/conflicts/ResourceDetailsPanel";
import { useArchiveConflictSummaries } from "@/hooks/queries";
import { usePreferMod, usePreferModPreview, useReindexConflicts, useToggleMod } from "@/hooks/mutations";
import type { ArchiveConflictSummaryOut, PreferModResult } from "@/types/api";

interface Props {
  gameName: string;
}

type SeverityFilter = "all" | "high" | "medium" | "low";
type ConflictTypeFilter = "all" | "real" | "cosmetic";

const SEVERITY_CHIPS: { key: SeverityFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "high", label: "High" },
  { key: "medium", label: "Medium" },
  { key: "low", label: "Low" },
];

const TYPE_CHIPS: { key: ConflictTypeFilter; label: string }[] = [
  { key: "all", label: "All types" },
  { key: "real", label: "Real" },
  { key: "cosmetic", label: "Cosmetic" },
];

const HEX_PATTERN = /^0x[0-9a-fA-F]{4,16}$/;

const SEVERITY_VARIANT: Record<string, "danger" | "warning" | "success"> = {
  high: "danger",
  medium: "warning",
  low: "success",
};

interface PreferPreviewState {
  winnerId: number;
  loserId: number;
  winnerName: string;
  loserName: string;
}

export function ArchiveResourceConflicts({ gameName }: Props) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<SeverityFilter>("all");
  const [typeFilter, setTypeFilter] = useState<ConflictTypeFilter>("all");

  // When the search looks like a hex resource hash, pass it to the backend
  const resourceHash = HEX_PATTERN.test(search.trim()) ? search.trim() : undefined;

  const { data: result, isLoading } = useArchiveConflictSummaries(gameName, resourceHash);
  const reindex = useReindexConflicts();
  const toggleMod = useToggleMod();
  const preferPreview = usePreferModPreview();
  const preferMod = usePreferMod();
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [detailsOpenFor, setDetailsOpenFor] = useState<{
    archive: string;
    filter: "all" | "real" | "cosmetic";
  } | null>(null);
  const [previewState, setPreviewState] = useState<PreferPreviewState | null>(null);
  const [previewResult, setPreviewResult] = useState<PreferModResult | null>(null);

  const summaries = result?.summaries ?? [];

  const filtered = useMemo(() => {
    let items = summaries;

    if (filter !== "all") {
      items = items.filter((s) => s.severity === filter);
    }

    if (typeFilter === "real") {
      items = items.filter((s) => s.real_count > 0);
    } else if (typeFilter === "cosmetic") {
      items = items.filter((s) => s.identical_count > 0 && s.real_count === 0);
    }

    // Text search (skip when search is a resource hash — already filtered server-side)
    if (search && !resourceHash) {
      const q = search.toLowerCase();
      items = items.filter(
        (s) =>
          s.archive_filename.toLowerCase().includes(q) ||
          s.mod_name?.toLowerCase().includes(q) ||
          s.conflicting_archives.some((a) => a.toLowerCase().includes(q)),
      );
    }

    return items;
  }, [summaries, filter, typeFilter, search, resourceHash]);

  const chipCounts = useMemo(() => {
    const all = summaries.length;
    const high = summaries.filter((s) => s.severity === "high").length;
    const medium = summaries.filter((s) => s.severity === "medium").length;
    const low = summaries.filter((s) => s.severity === "low").length;
    return { all, high, medium, low };
  }, [summaries]);

  const typeCounts = useMemo(() => ({
    all: summaries.length,
    real: summaries.filter((s) => s.real_count > 0).length,
    cosmetic: summaries.filter((s) => s.identical_count > 0 && s.real_count === 0).length,
  }), [summaries]);

  const toggleExpand = useCallback((filename: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(filename)) {
        next.delete(filename);
        setDetailsOpenFor((cur) => (cur?.archive === filename ? null : cur));
      } else {
        next.add(filename);
      }
      return next;
    });
  }, []);

  const openDetails = useCallback(
    (archive: string, filter: "all" | "real" | "cosmetic") => {
      setExpandedRows((prev) => {
        const next = new Set(prev);
        next.add(archive);
        return next;
      });
      setDetailsOpenFor({ archive, filter });
    },
    [],
  );

  const handlePrefer = useCallback(
    async (winnerId: number, loserId: number, winnerName: string, loserName: string) => {
      setPreviewState({ winnerId, loserId, winnerName, loserName });
      try {
        const result = await preferPreview.mutateAsync({
          gameName,
          data: { winner_mod_id: winnerId, loser_mod_id: loserId },
        });
        setPreviewResult(result);
      } catch {
        setPreviewState(null);
        setPreviewResult(null);
      }
    },
    [gameName, preferPreview],
  );

  const handleConfirmPrefer = useCallback(async () => {
    if (!previewState) return;
    try {
      await preferMod.mutateAsync({
        gameName,
        data: { winner_mod_id: previewState.winnerId, loser_mod_id: previewState.loserId },
      });
      setPreviewState(null);
      setPreviewResult(null);
    } catch {
      // Dialog stays open so the user can retry or cancel.
    }
  }, [gameName, previewState, preferMod]);

  const handleCancelPrefer = useCallback(() => {
    setPreviewState(null);
    setPreviewResult(null);
  }, []);

  // Build a lookup: archive_filename → summary for showing conflict partners
  const summaryMap = useMemo(() => {
    const map = new Map<string, ArchiveConflictSummaryOut>();
    for (const s of summaries) {
      map.set(s.archive_filename, s);
    }
    return map;
  }, [summaries]);

  if (isLoading) {
    return <SkeletonTable columns={5} />;
  }

  if (!result || summaries.length === 0) {
    return (
      <div className="space-y-4">
        <div className="flex justify-end">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => reindex.mutate(gameName)}
            loading={reindex.isPending}
          >
            <RefreshCw size={14} /> Reindex
          </Button>
        </div>
        <EmptyState
          icon={CheckCircle}
          title="No Archive Resource Conflicts"
          description="No .archive files share internal resource hashes. Click Reindex to scan for conflicts."
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <SearchInput value={search} onChange={setSearch} placeholder="Filter by name or resource hash (0x...)" />
        <FilterChips
          chips={SEVERITY_CHIPS.map((c) => ({ ...c, count: chipCounts[c.key] }))}
          active={filter}
          onChange={(v) => setFilter(v as SeverityFilter)}
        />
        <FilterChips
          chips={TYPE_CHIPS.map((c) => ({ ...c, count: typeCounts[c.key] }))}
          active={typeFilter}
          onChange={(v) => setTypeFilter(v as ConflictTypeFilter)}
        />
        <div className="flex items-center gap-2 ml-auto">
          <div className="flex items-center gap-2 text-xs text-text-muted mr-2">
            <ShieldAlert size={14} className="text-warning" />
            <span>
              {result.total_archives_with_conflicts} archive{result.total_archives_with_conflicts !== 1 ? "s" : ""} with conflicts
            </span>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => reindex.mutate(gameName)}
            loading={reindex.isPending}
          >
            <RefreshCw size={14} /> Reindex
          </Button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="py-8 text-sm text-text-muted text-center">
          No conflicts matching current filters.
        </p>
      ) : (
        <VirtualTable
          items={filtered}
          estimateHeight={48}
          dynamicHeight
          remeasureDep={`${expandedRows.size}-${detailsOpenFor?.archive}-${detailsOpenFor?.filter}`}
          renderHead={() => (
            <tr className="border-b border-border text-left text-xs text-text-muted">
              <th className="pb-2 pr-4 font-medium w-8" />
              <th className="pb-2 pr-4 font-medium">Archive</th>
              <th className="pb-2 pr-4 font-medium">Mod</th>
              <th className="pb-2 pr-4 font-medium">Impact</th>
              <th className="pb-2 pr-4 font-medium">Conflicts</th>
              <th className="pb-2 pr-4 font-medium w-24">Severity</th>
              <th className="pb-2 font-medium">Actions</th>
            </tr>
          )}
          renderRow={(item: ArchiveConflictSummaryOut) => {
            const isExpanded = expandedRows.has(item.archive_filename);
            const totalConflicts = item.real_count + item.identical_count;
            const impactRatio = item.total_entries > 0
              ? ((item.winning_entries + item.losing_entries) / item.total_entries) * 100
              : 0;

            return (
              <>
                <tr
                  key={item.archive_filename}
                  className="border-b border-border/50 hover:bg-surface-1 transition-colors cursor-pointer"
                  onClick={() => toggleExpand(item.archive_filename)}
                >
                  <td className="py-2.5 pr-2">
                    {isExpanded ? (
                      <ChevronDown size={14} className="text-text-muted" />
                    ) : (
                      <ChevronRight size={14} className="text-text-muted" />
                    )}
                  </td>
                  <td className="py-2.5 pr-4">
                    <code className="text-xs text-accent font-mono">{item.archive_filename}</code>
                  </td>
                  <td className="py-2.5 pr-4">
                    <span className="text-sm text-text-primary truncate block max-w-[180px]">
                      {item.mod_name ?? "Unmanaged"}
                    </span>
                  </td>
                  <td className="py-2.5 pr-4">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-text-secondary whitespace-nowrap">
                        <span className="text-success">{item.winning_entries}W</span>
                        {" / "}
                        <span className="text-danger">{item.losing_entries}L</span>
                        {" of "}
                        {item.total_entries}
                      </span>
                      <div className="w-16 h-1.5 bg-surface-2 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-accent rounded-full"
                          style={{ width: `${Math.min(impactRatio, 100)}%` }}
                        />
                      </div>
                    </div>
                  </td>
                  <td className="py-2.5 pr-4" onClick={(e) => e.stopPropagation()}>
                    <div className="space-y-1">
                      <span className="text-xs text-text-secondary">
                        {item.real_count > 0 && (
                          <button
                            className="text-danger hover:underline"
                            onClick={() => openDetails(item.archive_filename, "real")}
                          >
                            {item.real_count} real
                          </button>
                        )}
                        {item.real_count > 0 && item.identical_count > 0 && ", "}
                        {item.identical_count > 0 && (
                          <button
                            className="text-text-muted hover:underline"
                            onClick={() => openDetails(item.archive_filename, "cosmetic")}
                          >
                            {item.identical_count} cosmetic
                          </button>
                        )}
                        {totalConflicts === 0 && "—"}
                      </span>
                      {totalConflicts > 0 && (
                        <div className="flex h-1 w-12 rounded-full overflow-hidden bg-surface-2">
                          <div
                            className="bg-danger h-full"
                            style={{ width: `${(item.real_count / totalConflicts) * 100}%` }}
                          />
                          <div
                            className="bg-success/30 h-full"
                            style={{ width: `${(item.identical_count / totalConflicts) * 100}%` }}
                          />
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="py-2.5 pr-4">
                    <Badge
                      variant={SEVERITY_VARIANT[item.severity] ?? "neutral"}
                      title={
                        item.severity === "high"
                          ? "Over 50% of resources are being overridden by another archive"
                          : item.severity === "medium"
                            ? "Some resources are being overridden"
                            : "This archive wins all conflicts or has only cosmetic differences"
                      }
                    >
                      {item.severity}
                    </Badge>
                  </td>
                  <td className="py-2.5">
                    <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                      {item.installed_mod_id != null && item.losing_entries > 0 && (() => {
                        const conflictPartner = item.conflicting_archives[0];
                        const partner = conflictPartner ? summaryMap.get(conflictPartner) : undefined;
                        if (!partner?.installed_mod_id) return null;
                        const targetName = partner.mod_name ?? partner.archive_filename;
                        return (
                          <Button
                            variant="secondary"
                            size="sm"
                            title={`Prefer over "${targetName}" (demote its archives)`}
                            onClick={() =>
                              handlePrefer(
                                item.installed_mod_id!,
                                partner.installed_mod_id!,
                                item.mod_name ?? item.archive_filename,
                                targetName,
                              )
                            }
                          >
                            <Crown size={12} /> Prefer
                          </Button>
                        );
                      })()}
                      {item.installed_mod_id != null && (
                        <Button
                          variant="secondary"
                          size="sm"
                          title="Disable this mod"
                          onClick={() => toggleMod.mutate({ gameName, modId: item.installed_mod_id! })}
                        >
                          <Power size={12} />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
                {isExpanded && (
                  <tr className="bg-surface-1/50">
                    <td colSpan={7} className="px-8 py-3">
                      <div className="text-xs space-y-1.5">
                        {item.losing_entries > 0 && item.real_count > 0 && (
                          <p className="text-warning/80 flex items-center gap-1 mb-2">
                            <AlertTriangle size={12} />
                            This archive is losing {item.real_count} real conflict{item.real_count !== 1 ? "s" : ""}.
                            Use &quot;Prefer&quot; to change load order, or disable the conflicting mod.
                          </p>
                        )}
                        <p className="text-text-muted font-medium mb-2">
                          Conflicting archives ({item.conflicting_archives.length}):
                        </p>
                        {item.conflicting_archives.map((conflictArchive) => {
                          const partner = summaryMap.get(conflictArchive);
                          // First-loaded-wins: lower ASCII filename wins
                          const isWinner = item.archive_filename.toLowerCase() < conflictArchive.toLowerCase();
                          return (
                            <div
                              key={conflictArchive}
                              className="flex items-center gap-2 text-text-secondary"
                            >
                              <Shuffle size={12} className="text-text-muted shrink-0" />
                              <code className="font-mono text-accent">{conflictArchive}</code>
                              {partner?.mod_name && (
                                <span className="text-text-muted">({partner.mod_name})</span>
                              )}
                              {isWinner ? (
                                <Badge variant="success">wins over</Badge>
                              ) : (
                                <Badge variant="danger">loses to</Badge>
                              )}
                            </div>
                          );
                        })}

                        <button
                          className="flex items-center gap-1 mt-2 text-xs text-accent hover:text-accent/80 transition-colors"
                          onClick={() =>
                            setDetailsOpenFor((cur) =>
                              cur?.archive === item.archive_filename
                                ? null
                                : { archive: item.archive_filename, filter: "all" },
                            )
                          }
                        >
                          <List size={12} />
                          {detailsOpenFor?.archive === item.archive_filename ? "Hide" : "Show"} Resource Details
                          ({totalConflicts} conflict{totalConflicts !== 1 ? "s" : ""})
                        </button>

                        {detailsOpenFor?.archive === item.archive_filename && (
                          <ResourceDetailsPanel
                            gameName={gameName}
                            archiveFilename={item.archive_filename}
                            initialFilter={detailsOpenFor.filter}
                          />
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            );
          }}
        />
      )}

      {/* Prefer Preview Dialog */}
      {previewState && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
          onClick={handleCancelPrefer}
        >
          <div
            className="w-full max-w-md rounded-xl border border-border bg-surface-1 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 mb-4 text-accent">
              <Crown size={20} />
              <h3 className="text-lg font-semibold text-text-primary">
                Prefer &ldquo;{previewState.winnerName}&rdquo;
              </h3>
            </div>

            <p className="text-sm text-text-secondary mb-4">
              This will rename <strong>{previewState.loserName}</strong>&apos;s archives so they
              load after <strong>{previewState.winnerName}</strong>, making the winner&apos;s
              resources take priority.
            </p>

            {preferPreview.isPending && (
              <p className="text-sm text-text-muted py-4 text-center">Computing renames...</p>
            )}

            {previewResult && (
              <div className="space-y-2 mb-4">
                {previewResult.renames.length === 0 ? (
                  <p className="text-sm text-success">{previewResult.message}</p>
                ) : (
                  <>
                    <p className="text-xs text-text-muted font-medium">
                      Planned renames ({previewResult.renames.length}):
                    </p>
                    <div className="max-h-48 overflow-y-auto space-y-1 rounded border border-border p-2 bg-surface-0">
                      {previewResult.renames.map((r) => (
                        <div key={r.old_filename} className="text-xs font-mono">
                          <span className="text-danger">{r.old_filename}</span>
                          <span className="text-text-muted"> → </span>
                          <span className="text-success">{r.new_filename}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={preferMod.isPending}
                onClick={handleCancelPrefer}
              >
                Cancel
              </Button>
              {previewResult && previewResult.renames.length > 0 && (
                <Button
                  variant="primary"
                  size="sm"
                  loading={preferMod.isPending}
                  onClick={handleConfirmPrefer}
                >
                  Apply {previewResult.renames.length} rename{previewResult.renames.length !== 1 ? "s" : ""}
                </Button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
