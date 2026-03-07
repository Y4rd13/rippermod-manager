import { ChevronDown, ChevronRight, ExternalLink, Loader2, Power } from "lucide-react";
import { useMemo, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { FilterChips } from "@/components/ui/FilterChips";
import { DisableConfirmDialog } from "@/components/conflicts/DisableConfirmDialog";
import { useArchiveResourceDetails } from "@/hooks/queries";
import type { ResourceConflictDetail, ResourceConflictGroup } from "@/types/api";

type ResourceFilter = "all" | "real" | "cosmetic" | "dependency";

const FILTER_CHIPS: { key: ResourceFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "real", label: "Real" },
  { key: "dependency", label: "Dependency" },
  { key: "cosmetic", label: "Cosmetic" },
];

const HASH_COLLAPSE_THRESHOLD = 5;

interface Props {
  gameName: string;
  gameDomain: string;
  archiveFilename: string;
  initialFilter?: ResourceFilter;
}

interface DisableConfirmState {
  modId: number;
  modName: string;
  partnerArchive: string;
  realCount: number;
  cosmeticCount: number;
  dependencyCount: number;
}

function filterResources(
  resources: ResourceConflictDetail[],
  filter: ResourceFilter,
): ResourceConflictDetail[] {
  if (filter === "all") return resources;
  if (filter === "real") return resources.filter((r) => !r.is_identical && !r.is_dependency);
  if (filter === "dependency") return resources.filter((r) => r.is_dependency && !r.is_identical);
  return resources.filter((r) => r.is_identical);
}

function ResourceHashList({ resources }: { resources: ResourceConflictDetail[] }) {
  const [expanded, setExpanded] = useState(resources.length <= HASH_COLLAPSE_THRESHOLD);
  const shown = expanded ? resources : resources.slice(0, HASH_COLLAPSE_THRESHOLD);
  const remaining = resources.length - HASH_COLLAPSE_THRESHOLD;

  return (
    <div className="mt-2 ml-1 space-y-0.5">
      {shown.map((r) => (
        <div
          key={`${r.resource_hash}-${r.winner_archive}`}
          className="flex items-center gap-2 text-xs text-text-secondary py-0.5"
        >
          <code className="font-mono text-text-primary/80 text-[11px]">{r.resource_hash}</code>
          {r.is_identical ? (
            <Badge variant="success">cosmetic</Badge>
          ) : r.is_dependency ? (
            <Badge variant="warning">dependency</Badge>
          ) : (
            <Badge variant="danger">real</Badge>
          )}
        </div>
      ))}
      {!expanded && remaining > 0 && (
        <button
          className="text-xs text-accent hover:text-accent/80 transition-colors mt-1"
          onClick={() => setExpanded(true)}
        >
          Show {remaining} more hash{remaining !== 1 ? "es" : ""}...
        </button>
      )}
      {expanded && resources.length > HASH_COLLAPSE_THRESHOLD && (
        <button
          className="text-xs text-text-muted hover:text-text-secondary transition-colors mt-1"
          onClick={() => setExpanded(false)}
        >
          Show less
        </button>
      )}
    </div>
  );
}

function GroupSection({
  group,
  filter,
  collapsed,
  onToggle,
  gameDomain,
  onRequestDisable,
}: {
  group: ResourceConflictGroup;
  filter: ResourceFilter;
  collapsed: boolean;
  onToggle: () => void;
  gameDomain: string;
  onRequestDisable: (state: DisableConfirmState) => void;
}) {
  const filtered = filterResources(group.resources, filter);
  if (filtered.length === 0) return null;

  return (
    <div className="rounded-lg border border-border/40 bg-surface-0/50 overflow-hidden">
      {/* Card header */}
      <div className="flex items-center gap-3 px-3 py-2">
        <button
          className="flex-1 min-w-0 text-left"
          onClick={onToggle}
        >
          <div className="flex items-center gap-2">
            {collapsed ? (
              <ChevronRight size={12} className="text-text-muted shrink-0" />
            ) : (
              <ChevronDown size={12} className="text-text-muted shrink-0" />
            )}
            <code className="font-mono text-accent text-xs truncate">{group.partner_archive}</code>
            {group.is_winner ? (
              <Badge variant="success">wins over</Badge>
            ) : (
              <Badge variant="danger">loses to</Badge>
            )}
          </div>
          <div className="flex items-center gap-2 ml-5 mt-0.5">
            {group.partner_mod_name ? (
              <span className="text-text-muted text-xs truncate">{group.partner_mod_name}</span>
            ) : (
              <span className="text-text-muted/50 text-xs">Unmanaged</span>
            )}
            <span className="text-[10px] text-text-muted/60">
              {filtered.length} conflict{filtered.length !== 1 ? "s" : ""}
              {group.real_count > 0 && <span className="text-danger ml-1">{group.real_count} real</span>}
              {group.dependency_count > 0 && <span className="text-warning ml-1">{group.dependency_count} dep</span>}
              {group.identical_count > 0 && <span className="ml-1">{group.identical_count} cosmetic</span>}
            </span>
          </div>
        </button>
        <div className="flex items-center gap-1 shrink-0">
          {group.partner_nexus_mod_id != null && (
            <button
              className="rounded p-1.5 text-text-muted hover:text-accent hover:bg-surface-2 transition-colors"
              title="View on Nexus Mods"
              onClick={() =>
                openUrl(`https://www.nexusmods.com/${gameDomain}/mods/${group.partner_nexus_mod_id}`).catch(() => {})
              }
            >
              <ExternalLink size={12} />
            </button>
          )}
          {group.partner_installed_mod_id != null && (
            <Button
              variant="secondary"
              size="sm"
              title={`Disable ${group.partner_mod_name ?? group.partner_archive}`}
              onClick={() =>
                onRequestDisable({
                  modId: group.partner_installed_mod_id!,
                  modName: group.partner_mod_name ?? group.partner_archive,
                  partnerArchive: group.partner_archive,
                  realCount: group.real_count,
                  cosmeticCount: group.identical_count,
                  dependencyCount: group.dependency_count,
                })
              }
            >
              <Power size={10} />
            </Button>
          )}
        </div>
      </div>

      {/* Collapsible resource hashes */}
      {!collapsed && (
        <div className="border-t border-border/30 px-3 pb-2">
          <ResourceHashList resources={filtered} />
        </div>
      )}
    </div>
  );
}

export function ResourceDetailsPanel({ gameName, gameDomain, archiveFilename, initialFilter = "all" }: Props) {
  const { data, isLoading, isError } = useArchiveResourceDetails(gameName, archiveFilename);
  const [resourceFilter, setResourceFilter] = useState<ResourceFilter>(initialFilter);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [disableConfirm, setDisableConfirm] = useState<DisableConfirmState | null>(null);

  const counts = useMemo(() => {
    if (!data) return { all: 0, real: 0, dependency: 0, cosmetic: 0 };
    const all = data.groups.reduce((s, g) => s + g.resources.length, 0);
    const real = data.groups.reduce((s, g) => s + g.real_count, 0);
    const dependency = data.groups.reduce((s, g) => s + g.dependency_count, 0);
    const cosmetic = data.groups.reduce((s, g) => s + g.identical_count, 0);
    return { all, real, dependency, cosmetic };
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
  const depPct = counts.all > 0 ? (counts.dependency / counts.all) * 100 : 0;
  const cosmeticPct = counts.all > 0 ? (counts.cosmetic / counts.all) * 100 : 0;

  return (
    <div className="rounded border border-border bg-surface-0 mt-2 max-w-2xl">
      {/* Summary + Filters */}
      <div className="p-3 border-b border-border/30 space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xs font-medium text-text-primary">
            {counts.all} resource conflict{counts.all !== 1 ? "s" : ""}
          </span>
          <div className="flex h-1.5 w-20 rounded-full overflow-hidden bg-surface-2">
            <div className="bg-danger h-full" style={{ width: `${realPct}%` }} />
            <div className="bg-warning/50 h-full" style={{ width: `${depPct}%` }} />
            <div className="bg-success/30 h-full" style={{ width: `${cosmeticPct}%` }} />
          </div>
          <span className="text-xs text-text-muted">
            {counts.real > 0 && <span className="text-danger">{counts.real} real</span>}
            {counts.real > 0 && counts.dependency > 0 && ", "}
            {counts.dependency > 0 && <span className="text-warning">{counts.dependency} dependency</span>}
            {(counts.real > 0 || counts.dependency > 0) && counts.cosmetic > 0 && ", "}
            {counts.cosmetic > 0 && <span>{counts.cosmetic} cosmetic</span>}
          </span>
        </div>
        <FilterChips
          chips={FILTER_CHIPS.map((c) => ({ ...c, count: counts[c.key] }))}
          active={resourceFilter}
          onChange={(v) => setResourceFilter(v as ResourceFilter)}
        />
      </div>

      {/* Groups */}
      <div className="max-h-72 overflow-y-auto p-3 space-y-2">
        {data.groups.map((group) => (
          <GroupSection
            key={group.partner_archive}
            group={group}
            filter={resourceFilter}
            collapsed={collapsedGroups.has(group.partner_archive)}
            onToggle={() => toggleGroup(group.partner_archive)}
            gameDomain={gameDomain}
            onRequestDisable={setDisableConfirm}
          />
        ))}
      </div>

      {/* Disable Confirmation Dialog */}
      {disableConfirm && (
        <DisableConfirmDialog
          gameName={gameName}
          modId={disableConfirm.modId}
          modName={disableConfirm.modName}
          onClose={() => setDisableConfirm(null)}
        >
          <p>
            The following conflicts with{" "}
            <code className="text-xs bg-surface-2 px-1 rounded">{archiveFilename}</code>{" "}
            will be resolved:
          </p>
          <div className="rounded border border-border p-2 bg-surface-0 space-y-1">
            {disableConfirm.realCount > 0 && (
              <div className="flex items-center gap-2 text-xs">
                <Badge variant="danger">real</Badge>
                <span>{disableConfirm.realCount} conflict{disableConfirm.realCount !== 1 ? "s" : ""}</span>
              </div>
            )}
            {disableConfirm.dependencyCount > 0 && (
              <div className="flex items-center gap-2 text-xs">
                <Badge variant="warning">dependency</Badge>
                <span>{disableConfirm.dependencyCount} conflict{disableConfirm.dependencyCount !== 1 ? "s" : ""}</span>
              </div>
            )}
            {disableConfirm.cosmeticCount > 0 && (
              <div className="flex items-center gap-2 text-xs">
                <Badge variant="success">cosmetic</Badge>
                <span>{disableConfirm.cosmeticCount} conflict{disableConfirm.cosmeticCount !== 1 ? "s" : ""}</span>
              </div>
            )}
          </div>
        </DisableConfirmDialog>
      )}
    </div>
  );
}
