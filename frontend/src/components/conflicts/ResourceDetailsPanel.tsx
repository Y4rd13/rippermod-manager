import { ChevronDown, ChevronRight, Loader2, Shuffle } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { FilterChips } from "@/components/ui/FilterChips";
import { useArchiveResourceDetails } from "@/hooks/queries";
import type { ResourceConflictDetail, ResourceConflictGroup } from "@/types/api";

type ResourceFilter = "all" | "real" | "cosmetic";

const FILTER_CHIPS: { key: ResourceFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "real", label: "Real" },
  { key: "cosmetic", label: "Cosmetic" },
];

interface Props {
  gameName: string;
  archiveFilename: string;
  initialFilter?: ResourceFilter;
}

function filterResources(
  resources: ResourceConflictDetail[],
  filter: ResourceFilter,
): ResourceConflictDetail[] {
  if (filter === "all") return resources;
  if (filter === "real") return resources.filter((r) => !r.is_identical);
  return resources.filter((r) => r.is_identical);
}

function GroupSection({
  group,
  filter,
  collapsed,
  onToggle,
}: {
  group: ResourceConflictGroup;
  filter: ResourceFilter;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const filtered = filterResources(group.resources, filter);
  if (filtered.length === 0) return null;

  return (
    <div className="border-b border-border/30 last:border-b-0 pb-2 last:pb-0">
      <button
        className="flex items-center gap-2 flex-wrap w-full text-left"
        onClick={onToggle}
      >
        {collapsed ? (
          <ChevronRight size={12} className="text-text-muted shrink-0" />
        ) : (
          <ChevronDown size={12} className="text-text-muted shrink-0" />
        )}
        <code className="font-mono text-accent text-xs">{group.partner_archive}</code>
        {group.partner_mod_name && (
          <span className="text-text-muted text-xs">({group.partner_mod_name})</span>
        )}
        {group.is_winner ? (
          <Badge variant="success">wins over</Badge>
        ) : (
          <Badge variant="danger">loses to</Badge>
        )}
        <span className="text-xs text-text-muted ml-auto">
          {filtered.length} conflict{filtered.length !== 1 ? "s" : ""}
        </span>
      </button>

      {!collapsed && (
        <div className="space-y-0.5 mt-1.5 ml-5">
          {filtered.map((r) => (
            <div
              key={`${r.resource_hash}-${r.winner_archive}`}
              className="flex items-center gap-2 text-xs text-text-secondary"
            >
              <Shuffle size={10} className="text-text-muted shrink-0" />
              <code className="font-mono text-text-primary">{r.resource_hash}</code>
              {r.is_identical ? (
                <Badge variant="success">cosmetic</Badge>
              ) : (
                <Badge variant="danger">real</Badge>
              )}
              <span className="text-text-muted truncate">winner: {r.winner_archive}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ResourceDetailsPanel({ gameName, archiveFilename, initialFilter = "all" }: Props) {
  const { data, isLoading, isError } = useArchiveResourceDetails(gameName, archiveFilename);
  const [resourceFilter, setResourceFilter] = useState<ResourceFilter>(initialFilter);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  const counts = useMemo(() => {
    if (!data) return { all: 0, real: 0, cosmetic: 0 };
    const all = data.groups.reduce((s, g) => s + g.resources.length, 0);
    const real = data.groups.reduce((s, g) => s + g.real_count, 0);
    const cosmetic = data.groups.reduce((s, g) => s + g.identical_count, 0);
    return { all, real, cosmetic };
  }, [data]);

  const toggleGroup = (partner: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(partner)) next.delete(partner);
      else next.add(partner);
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-3 text-xs text-text-muted">
        <Loader2 size={14} className="animate-spin" />
        Loading resource details...
      </div>
    );
  }

  if (isError || !data) {
    return (
      <p className="py-2 text-xs text-danger">Failed to load resource details.</p>
    );
  }

  if (data.groups.length === 0) {
    return (
      <p className="py-2 text-xs text-text-muted">No resource-level conflict details available.</p>
    );
  }

  const realPct = counts.all > 0 ? (counts.real / counts.all) * 100 : 0;
  const cosmeticPct = counts.all > 0 ? (counts.cosmetic / counts.all) * 100 : 0;

  return (
    <div className="rounded border border-border bg-surface-0 mt-2">
      {/* Summary + Filters */}
      <div className="p-3 border-b border-border/30 space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xs font-medium text-text-primary">
            {counts.all} resource conflict{counts.all !== 1 ? "s" : ""}
          </span>
          <div className="flex h-1.5 w-20 rounded-full overflow-hidden bg-surface-2">
            <div className="bg-danger h-full" style={{ width: `${realPct}%` }} />
            <div className="bg-success/30 h-full" style={{ width: `${cosmeticPct}%` }} />
          </div>
          <span className="text-xs text-text-muted">
            {counts.real > 0 && <span className="text-danger">{counts.real} real</span>}
            {counts.real > 0 && counts.cosmetic > 0 && ", "}
            {counts.cosmetic > 0 && <span>{counts.cosmetic} cosmetic</span>}
          </span>
        </div>
        <FilterChips
          chips={FILTER_CHIPS.map((c) => ({ ...c, count: counts[c.key] }))}
          active={resourceFilter}
          onChange={(v) => setResourceFilter(v as ResourceFilter)}
        />
        <details className="text-xs text-text-muted">
          <summary className="cursor-pointer text-accent hover:text-accent/80 transition-colors">
            What does this mean?
          </summary>
          <div className="mt-1.5 p-2 rounded bg-surface-2 space-y-1.5">
            <p>
              <Badge variant="success">cosmetic</Badge>{" "}
              Both archives contain identical data for this resource. No gameplay impact — safe to ignore.
            </p>
            <p>
              <Badge variant="danger">real</Badge>{" "}
              Archives contain different data. The winner&apos;s version is used in-game. Change load order if you want the other version.
            </p>
          </div>
        </details>
      </div>

      {/* Groups */}
      <div className="max-h-64 overflow-y-auto p-3 space-y-2">
        {data.groups.map((group) => (
          <GroupSection
            key={group.partner_archive}
            group={group}
            filter={resourceFilter}
            collapsed={collapsedGroups.has(group.partner_archive)}
            onToggle={() => toggleGroup(group.partner_archive)}
          />
        ))}
      </div>
    </div>
  );
}
