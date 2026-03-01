import { CheckCircle, RefreshCw, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { SearchInput } from "@/components/ui/SearchInput";
import { SkeletonTable } from "@/components/ui/SkeletonTable";
import { VirtualTable } from "@/components/ui/VirtualTable";
import { useConflictSummary } from "@/hooks/queries";
import { useReindexConflicts } from "@/hooks/mutations";
import type { ConflictEvidenceOut } from "@/types/api";

interface Props {
  gameName: string;
}

type SeverityFilter = "all" | "high" | "medium" | "low";

const FILTER_CHIPS: { key: SeverityFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "high", label: "High" },
  { key: "medium", label: "Medium" },
  { key: "low", label: "Low" },
];

const SEVERITY_VARIANT: Record<string, "danger" | "warning" | "success"> = {
  high: "danger",
  medium: "warning",
  low: "success",
};

export function ArchiveResourceConflicts({ gameName }: Props) {
  const { data: summary, isLoading } = useConflictSummary(gameName, "archive_resource");
  const reindex = useReindexConflicts();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<SeverityFilter>("all");

  const filtered = useMemo(() => {
    if (!summary) return [];
    let items = summary.evidence;

    if (filter !== "all") {
      items = items.filter((e) => e.severity === filter);
    }

    if (search) {
      const q = search.toLowerCase();
      items = items.filter(
        (e) =>
          e.key.toLowerCase().includes(q) ||
          e.mods.some((m) => m.name.toLowerCase().includes(q)) ||
          e.detail.winner_archive?.toString().toLowerCase().includes(q),
      );
    }

    return items;
  }, [summary, filter, search]);

  const chipCounts = useMemo(() => {
    if (!summary) return {};
    const all = summary.evidence.length;
    const high = summary.evidence.filter((e) => e.severity === "high").length;
    const medium = summary.evidence.filter((e) => e.severity === "medium").length;
    const low = summary.evidence.filter((e) => e.severity === "low").length;
    return { all, high, medium, low };
  }, [summary]);

  if (isLoading) {
    return <SkeletonTable columns={5} />;
  }

  if (!summary || summary.evidence.length === 0) {
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
      <div className="flex items-center gap-3">
        <SearchInput value={search} onChange={setSearch} placeholder="Filter by hash, mod, or archive..." />
        <FilterChips
          chips={FILTER_CHIPS.map((c) => ({ ...c, count: chipCounts[c.key] }))}
          active={filter}
          onChange={(v) => setFilter(v as SeverityFilter)}
        />
        <div className="flex items-center gap-2 ml-auto">
          <div className="flex items-center gap-2 text-xs text-text-muted mr-2">
            <ShieldAlert size={14} className="text-warning" />
            <span>
              {summary.total_conflicts} resource conflict{summary.total_conflicts !== 1 ? "s" : ""}
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
          renderHead={() => (
            <tr className="border-b border-border text-left text-xs text-text-muted">
              <th className="pb-2 pr-4 font-medium">Resource Hash</th>
              <th className="pb-2 pr-4 font-medium">Winner Archive</th>
              <th className="pb-2 pr-4 font-medium">Loser Archive(s)</th>
              <th className="pb-2 pr-4 font-medium w-24">Severity</th>
              <th className="pb-2 pr-4 font-medium">Mods</th>
            </tr>
          )}
          renderRow={(item: ConflictEvidenceOut) => {
            const detail = item.detail as { winner_archive?: string; loser_archives?: string[] };
            return (
              <tr
                key={item.id}
                className="border-b border-border/50 hover:bg-surface-1 transition-colors"
              >
                <td className="py-2.5 pr-4">
                  <code className="text-xs text-accent font-mono">{item.key}</code>
                </td>
                <td className="py-2.5 pr-4">
                  <span className="text-sm text-success truncate block max-w-[200px]">
                    {detail.winner_archive ?? "-"}
                  </span>
                </td>
                <td className="py-2.5 pr-4">
                  <span className="text-sm text-danger truncate block max-w-[250px]">
                    {detail.loser_archives?.join(", ") ?? "-"}
                  </span>
                </td>
                <td className="py-2.5 pr-4">
                  <Badge variant={SEVERITY_VARIANT[item.severity] ?? "neutral"}>
                    {item.severity}
                  </Badge>
                </td>
                <td className="py-2.5 pr-4">
                  <span className="text-xs text-text-muted truncate block max-w-xs">
                    {item.mods.map((m) => m.name).join(", ")}
                  </span>
                </td>
              </tr>
            );
          }}
        />
      )}
    </div>
  );
}
