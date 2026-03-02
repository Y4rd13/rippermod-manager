import { AlertTriangle, CheckCircle, ShieldAlert } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { ConflictDetailDrawer } from "@/components/mods/ConflictDetailDrawer";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { SearchInput } from "@/components/ui/SearchInput";
import { SkeletonTable } from "@/components/ui/SkeletonTable";
import { SortableHeader } from "@/components/ui/SortableHeader";
import { VirtualTable } from "@/components/ui/VirtualTable";
import { useConflictsOverview } from "@/hooks/queries";
import type { ConflictSeverity, ModConflictSummary } from "@/types/api";

interface Props {
  gameName: string;
}

type FilterKey = "all" | "critical" | "warning";

const FILTER_CHIPS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "critical", label: "Critical" },
  { key: "warning", label: "Warning" },
];

type InboxSortKey = "name" | "conflicts" | "severity";

const INBOX_SEVERITY_ORDER: Record<string, number> = { critical: 0, warning: 1, info: 2 };

const SEVERITY_VARIANT: Record<ConflictSeverity, "danger" | "warning" | "success"> = {
  critical: "danger",
  warning: "warning",
  info: "success",
};

export function ConflictsInbox({ gameName }: Props) {
  const { data: overview, isLoading } = useConflictsOverview(gameName);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [selectedMod, setSelectedMod] = useState<ModConflictSummary | null>(null);
  const [sortKey, setSortKey] = useState<InboxSortKey>("conflicts");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const handleSort = useCallback((key: string) => {
    const k = key as InboxSortKey;
    setSortDir((prev) => (sortKey === k ? (prev === "asc" ? "desc" : "asc") : "asc"));
    setSortKey(k);
  }, [sortKey]);

  const filtered = useMemo(() => {
    if (!overview) return [];
    let items = overview.summaries;

    if (filter !== "all") {
      items = items.filter((s) => s.severity === filter);
    }

    if (search) {
      const q = search.toLowerCase();
      items = items.filter((s) => s.mod_name.toLowerCase().includes(q));
    }

    items = [...items].sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "name":
          cmp = a.mod_name.localeCompare(b.mod_name);
          break;
        case "conflicts":
          cmp = a.conflict_count - b.conflict_count;
          break;
        case "severity":
          cmp = (INBOX_SEVERITY_ORDER[a.severity] ?? 3) - (INBOX_SEVERITY_ORDER[b.severity] ?? 3);
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });

    return items;
  }, [overview, filter, search, sortKey, sortDir]);

  const chipCounts = useMemo(() => {
    if (!overview) return {};
    const all = overview.summaries.length;
    const critical = overview.summaries.filter((s) => s.severity === "critical").length;
    const warning = overview.summaries.filter((s) => s.severity === "warning").length;
    return { all, critical, warning };
  }, [overview]);

  if (isLoading) {
    return <SkeletonTable columns={5} />;
  }

  if (!overview || overview.summaries.length === 0) {
    return (
      <EmptyState
        icon={CheckCircle}
        title="No File Conflicts"
        description="All installed mods have their files intact. No files have been overwritten by other mods."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <SearchInput value={search} onChange={setSearch} placeholder="Filter by mod name..." />
        <FilterChips
          chips={FILTER_CHIPS.map((c) => ({ ...c, count: chipCounts[c.key] }))}
          active={filter}
          onChange={(v) => setFilter(v as FilterKey)}
        />
        <div className="flex items-center gap-2 ml-auto text-xs text-text-muted">
          <ShieldAlert size={14} className="text-warning" />
          <span>
            {overview.total_conflicts} conflict{overview.total_conflicts !== 1 ? "s" : ""} across{" "}
            {overview.mods_affected} mod{overview.mods_affected !== 1 ? "s" : ""}
          </span>
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
          renderHead={() => (
            <tr className="border-b border-border text-left text-xs text-text-muted">
              <SortableHeader label="Mod Name" sortKey="name" activeSortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
              <SortableHeader label="Conflicts" sortKey="conflicts" activeSortKey={sortKey} sortDir={sortDir} onSort={handleSort} className="w-28" />
              <SortableHeader label="Severity" sortKey="severity" activeSortKey={sortKey} sortDir={sortDir} onSort={handleSort} className="w-24" />
              <th className="pb-2 pr-4 font-medium">Conflicting Mods</th>
            </tr>
          )}
          renderRow={(item) => (
            <tr
              key={item.mod_id}
              onClick={() => setSelectedMod(item)}
              className="border-b border-border/50 cursor-pointer hover:bg-surface-1 transition-colors"
            >
              <td className="py-2.5 pr-4">
                <div className="flex items-center gap-2">
                  <AlertTriangle
                    size={14}
                    className={item.severity === "critical" ? "text-danger shrink-0" : "text-warning shrink-0"}
                  />
                  <span className="text-sm text-text-primary truncate">{item.mod_name}</span>
                </div>
              </td>
              <td className="py-2.5 pr-4">
                <span className="text-sm tabular-nums text-text-secondary">
                  {item.conflict_count} / {item.total_archive_files}
                </span>
              </td>
              <td className="py-2.5 pr-4">
                <Badge variant={SEVERITY_VARIANT[item.severity]}>
                  {item.severity}
                </Badge>
              </td>
              <td className="py-2.5 pr-4">
                <span className="text-xs text-text-muted truncate block max-w-xs">
                  {item.conflicting_mod_names.join(", ")}
                </span>
              </td>
            </tr>
          )}
        />
      )}

      {selectedMod && (
        <ConflictDetailDrawer
          gameName={gameName}
          modId={selectedMod.mod_id}
          modName={selectedMod.mod_name}
          severity={selectedMod.severity}
          onClose={() => setSelectedMod(null)}
        />
      )}
    </div>
  );
}
