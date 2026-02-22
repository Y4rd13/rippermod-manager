import {
  ArrowUp,
  Copy,
  ExternalLink,
  Package,
  Power,
  PowerOff,
  Search,
  Trash2,
} from "lucide-react";
import { useMemo, useState } from "react";

import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { ModCardAction } from "@/components/mods/ModCardAction";
import { NexusModCard } from "@/components/mods/NexusModCard";
import { Badge, ConfidenceBadge } from "@/components/ui/Badge";
import { BulkActionBar } from "@/components/ui/BulkActionBar";
import { Button } from "@/components/ui/Button";
import { ContextMenu, type ContextMenuItem } from "@/components/ui/ContextMenu";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { SkeletonTable } from "@/components/ui/SkeletonTable";
import { SortSelect } from "@/components/ui/SortSelect";
import { useBulkSelect } from "@/hooks/use-bulk-select";
import { useContextMenu } from "@/hooks/use-context-menu";
import { useToggleMod, useUninstallMod } from "@/hooks/mutations";
import { useInstallFlow } from "@/hooks/use-install-flow";
import { isoToEpoch, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AvailableArchive, DownloadJobOut, InstalledModOut, ModGroup, ModUpdate } from "@/types/api";

interface Props {
  mods: InstalledModOut[];
  gameName: string;
  recognizedMods?: ModGroup[];
  archives?: AvailableArchive[];
  downloadJobs?: DownloadJobOut[];
  updates?: ModUpdate[];
  isLoading?: boolean;
  onModClick?: (nexusModId: number) => void;
  onTabChange?: (tab: string) => void;
}

type SortKey = "name" | "version" | "files" | "disabled" | "updated";

type RecognizedSortKey = "name" | "endorsements" | "updated" | "confidence";

type ChipKey = "all" | "enabled" | "disabled" | "has-update";

const CHIP_OPTIONS: { key: ChipKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "enabled", label: "Enabled" },
  { key: "disabled", label: "Disabled" },
  { key: "has-update", label: "Has Update" },
];

const RECOGNIZED_SORT_OPTIONS: { value: RecognizedSortKey; label: string }[] = [
  { value: "confidence", label: "Match Confidence" },
  { value: "name", label: "Mod Name" },
  { value: "endorsements", label: "Endorsements" },
  { value: "updated", label: "Recently Updated" },
];

function ManagedModsTable({
  mods,
  gameName,
  updateByInstalledId,
  updateByNexusId,
  onModClick,
}: {
  mods: InstalledModOut[];
  gameName: string;
  updateByInstalledId: Map<number, ModUpdate>;
  updateByNexusId: Map<number, ModUpdate>;
  onModClick?: (nexusModId: number) => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("updated");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [confirming, setConfirming] = useState<number | null>(null);
  const toggleMod = useToggleMod();
  const uninstallMod = useUninstallMod();

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sorted = useMemo(
    () =>
      [...mods].sort((a, b) => {
        const dir = sortDir === "asc" ? 1 : -1;
        switch (sortKey) {
          case "name":
            return a.name.localeCompare(b.name) * dir;
          case "version":
            return a.installed_version.localeCompare(b.installed_version) * dir;
          case "files":
            return (a.file_count - b.file_count) * dir;
          case "disabled":
            return (Number(a.disabled) - Number(b.disabled)) * dir;
          case "updated":
            return (isoToEpoch(a.nexus_updated_at) - isoToEpoch(b.nexus_updated_at)) * dir;
          default:
            return 0;
        }
      }),
    [mods, sortKey, sortDir],
  );

  const sortedIds = useMemo(() => sorted.map((m) => m.id), [sorted]);
  const bulk = useBulkSelect(sortedIds);

  const { menuState, openMenu, closeMenu } = useContextMenu<InstalledModOut>();

  const buildContextMenuItems = (mod: InstalledModOut): ContextMenuItem[] => {
    const items: ContextMenuItem[] = [
      {
        key: mod.disabled ? "enable" : "disable",
        label: mod.disabled ? "Enable" : "Disable",
        icon: mod.disabled ? Power : PowerOff,
      },
    ];
    if (mod.nexus_mod_id) {
      items.push({ key: "nexus", label: "View on Nexus", icon: ExternalLink });
    }
    items.push({ key: "copy", label: "Copy Name", icon: Copy });
    items.push({ key: "sep", label: "", separator: true });
    items.push({ key: "delete", label: "Delete", icon: Trash2, variant: "danger" });
    return items;
  };

  const handleContextMenuSelect = (key: string) => {
    const mod = menuState.data;
    if (!mod) return;
    switch (key) {
      case "enable":
      case "disable":
        toggleMod.mutate({ gameName, modId: mod.id });
        break;
      case "nexus":
        if (mod.nexus_mod_id) onModClick?.(mod.nexus_mod_id);
        break;
      case "copy":
        void navigator.clipboard.writeText(mod.name);
        break;
      case "delete":
        setConfirming(mod.id);
        break;
    }
  };

  const handleBulkEnable = async () => {
    const targets = sorted.filter((m) => bulk.selectedIds.has(m.id) && m.disabled);
    try {
      for (const mod of targets) {
        await toggleMod.mutateAsync({ gameName, modId: mod.id });
      }
    } finally {
      bulk.deselectAll();
    }
  };

  const handleBulkDisable = async () => {
    const targets = sorted.filter((m) => bulk.selectedIds.has(m.id) && !m.disabled);
    try {
      for (const mod of targets) {
        await toggleMod.mutateAsync({ gameName, modId: mod.id });
      }
    } finally {
      bulk.deselectAll();
    }
  };

  const handleBulkDelete = async () => {
    const targets = sorted.filter((m) => bulk.selectedIds.has(m.id));
    try {
      for (const mod of targets) {
        await uninstallMod.mutateAsync({ gameName, modId: mod.id });
      }
    } finally {
      bulk.deselectAll();
    }
  };

  const selectedMods = sorted.filter((m) => bulk.selectedIds.has(m.id));
  const hasDisabledSelected = selectedMods.some((m) => m.disabled);
  const hasEnabledSelected = selectedMods.some((m) => !m.disabled);

  return (
    <>
      <BulkActionBar
        selectedCount={bulk.selectedCount}
        totalCount={sorted.length}
        onSelectAll={bulk.selectAll}
        onDeselectAll={bulk.deselectAll}
        isAllSelected={bulk.isAllSelected}
      >
        {hasDisabledSelected && (
          <Button size="sm" variant="secondary" onClick={handleBulkEnable}>
            <Power size={12} className="mr-1" /> Enable
          </Button>
        )}
        {hasEnabledSelected && (
          <Button size="sm" variant="secondary" onClick={handleBulkDisable}>
            <PowerOff size={12} className="mr-1" /> Disable
          </Button>
        )}
        <Button size="sm" variant="danger" onClick={handleBulkDelete}>
          <Trash2 size={12} className="mr-1" /> Delete
        </Button>
      </BulkActionBar>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text-muted sticky top-0 z-10 bg-surface-0">
              <th className="py-2 pr-4 w-8">
                <input
                  type="checkbox"
                  checked={bulk.isAllSelected}
                  onChange={bulk.isAllSelected ? bulk.deselectAll : bulk.selectAll}
                  className="h-4 w-4 rounded accent-accent"
                />
              </th>
              {(
                [
                  ["name", "Mod Name"],
                  ["version", "Version"],
                  ["files", "Files"],
                  ["disabled", "Status"],
                  ["updated", "Updated"],
                ] as const
              ).map(([key, label]) => (
                <th
                  key={key}
                  className="cursor-pointer select-none py-2 pr-4 hover:text-text-primary"
                  onClick={() => handleSort(key)}
                >
                  {label} {sortKey === key && (sortDir === "asc" ? "^" : "v")}
                </th>
              ))}
              <th className="py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((mod) => {
              const update =
                updateByInstalledId.get(mod.id) ??
                (mod.nexus_mod_id ? updateByNexusId.get(mod.nexus_mod_id) : undefined);
              return (
                <tr
                  key={mod.id}
                  className={cn(
                    "border-b border-border/50",
                    mod.disabled && "opacity-50",
                    update && !mod.disabled && "bg-warning/5",
                    bulk.isSelected(mod.id) && "bg-accent/5",
                  )}
                  onContextMenu={(e) => openMenu(e, mod)}
                >
                  <td className="py-2 pr-4">
                    <input
                      type="checkbox"
                      checked={bulk.isSelected(mod.id)}
                      onChange={() => bulk.toggle(mod.id)}
                      onClick={(e) => e.stopPropagation()}
                      className="h-4 w-4 rounded accent-accent"
                    />
                  </td>
                  <td className="py-2 pr-4">
                    {mod.nexus_mod_id ? (
                      <button
                        className="text-text-primary hover:text-accent transition-colors text-left"
                        onClick={() => onModClick?.(mod.nexus_mod_id!)}
                      >
                        {mod.name}
                      </button>
                    ) : (
                      <span className="text-text-primary">{mod.name}</span>
                    )}
                    {mod.nexus_mod_id && (
                      <span className="ml-2 text-xs text-text-muted">#{mod.nexus_mod_id}</span>
                    )}
                  </td>
                  <td className="py-2 pr-4 text-text-muted">
                    <span>{mod.installed_version || "--"}</span>
                    {update && (
                      <Badge variant="warning" prominent className="ml-2">
                        <ArrowUp size={10} className="mr-0.5" />
                        v{update.nexus_version}
                      </Badge>
                    )}
                  </td>
                  <td className="py-2 pr-4 text-text-muted">{mod.file_count}</td>
                  <td className="py-2 pr-4">
                    <Badge variant={mod.disabled ? "danger" : "success"}>
                      {mod.disabled ? "Disabled" : "Enabled"}
                    </Badge>
                  </td>
                  <td className="py-2 pr-4 text-text-muted">
                    {mod.nexus_updated_at ? timeAgo(isoToEpoch(mod.nexus_updated_at)) : "—"}
                  </td>
                  <td className="py-2 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        title={mod.disabled ? "Enable this mod" : "Disable this mod"}
                        loading={toggleMod.isPending && toggleMod.variables?.modId === mod.id}
                        onClick={() => toggleMod.mutate({ gameName, modId: mod.id })}
                      >
                        {mod.disabled ? (
                          <Power size={14} className="text-success" />
                        ) : (
                          <PowerOff size={14} className="text-warning" />
                        )}
                      </Button>
                      {confirming === mod.id ? (
                        <Button
                          variant="danger"
                          size="sm"
                          loading={
                            uninstallMod.isPending && uninstallMod.variables?.modId === mod.id
                          }
                          onClick={() => {
                            uninstallMod.mutate({ gameName, modId: mod.id });
                            setConfirming(null);
                          }}
                        >
                          Confirm
                        </Button>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Uninstall this mod"
                          onClick={() => setConfirming(mod.id)}
                        >
                          <Trash2 size={14} className="text-danger" />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {menuState.visible && menuState.data && (
        <ContextMenu
          items={buildContextMenuItems(menuState.data)}
          position={menuState.position}
          onSelect={handleContextMenuSelect}
          onClose={closeMenu}
        />
      )}
    </>
  );
}

function RecognizedModsGrid({
  mods,
  archives,
  installedModIds,
  gameName,
  downloadJobs,
  updateByNexusId,
  onModClick,
}: {
  mods: ModGroup[];
  archives: AvailableArchive[];
  installedModIds: Set<number>;
  gameName: string;
  downloadJobs: DownloadJobOut[];
  updateByNexusId: Map<number, ModUpdate>;
  onModClick?: (nexusModId: number) => void;
}) {
  const flow = useInstallFlow(gameName, archives, downloadJobs);

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {mods.map((mod) => {
          const match = mod.nexus_match;
          if (!match) return null;

          const nexusModId = match.nexus_mod_id;
          const archive = nexusModId != null ? flow.archiveByModId.get(nexusModId) : undefined;
          const update = nexusModId != null ? updateByNexusId.get(nexusModId) : undefined;

          return (
            <NexusModCard
              key={mod.id}
              modName={match.mod_name}
              summary={match.summary}
              author={match.author}
              version={match.version}
              endorsementCount={match.endorsement_count}
              pictureUrl={match.picture_url}
              badge={update ? <Badge variant="warning" prominent>v{update.nexus_version} available</Badge> : undefined}
              onClick={nexusModId != null ? () => onModClick?.(nexusModId) : undefined}
              action={
                <ModCardAction
                  isInstalled={nexusModId != null && installedModIds.has(nexusModId)}
                  isInstalling={nexusModId != null && flow.installingModIds.has(nexusModId)}
                  activeDownload={nexusModId != null ? flow.activeDownloadByModId.get(nexusModId) : undefined}
                  completedDownload={nexusModId != null ? flow.completedDownloadByModId.get(nexusModId) : undefined}
                  archive={archive}
                  nexusUrl={match.nexus_url}
                  hasConflicts={flow.conflicts != null}
                  isDownloading={flow.downloadingModId === nexusModId}
                  isUpdate={!!update}
                  updateVersion={update?.nexus_version}
                  onInstall={() => nexusModId != null && archive && flow.handleInstall(nexusModId, archive)}
                  onInstallByFilename={() => {
                    const dl = nexusModId != null ? flow.completedDownloadByModId.get(nexusModId) : undefined;
                    if (nexusModId != null && dl) flow.handleInstallByFilename(nexusModId, dl.file_name);
                  }}
                  onDownload={() => nexusModId != null && flow.handleDownload(nexusModId)}
                  onCancelDownload={() => {
                    const dl = nexusModId != null ? flow.activeDownloadByModId.get(nexusModId) : undefined;
                    if (dl) flow.handleCancelDownload(dl.id);
                  }}
                />
              }
              footer={
                <div className="flex items-center gap-1.5">
                  <ConfidenceBadge score={match.score} />
                  <Badge variant="neutral">{match.method}</Badge>
                  {match.updated_at && (
                    <span className="text-xs text-text-muted">{timeAgo(isoToEpoch(match.updated_at))}</span>
                  )}
                </div>
              }
            />
          );
        })}
      </div>

      {flow.conflicts && (
        <ConflictDialog
          conflicts={flow.conflicts}
          onCancel={flow.dismissConflicts}
          onSkip={flow.handleInstallWithSkip}
          onOverwrite={flow.handleInstallOverwrite}
        />
      )}
    </>
  );
}

export function InstalledModsTable({
  mods,
  gameName,
  recognizedMods = [],
  archives = [],
  downloadJobs = [],
  updates = [],
  isLoading,
  onModClick,
  onTabChange,
}: Props) {
  const [filter, setFilter] = useState("");
  const [chip, setChip] = useState<ChipKey>("all");
  const [recognizedSort, setRecognizedSort] = useState<RecognizedSortKey>("updated");

  const updateByNexusId = useMemo(() => {
    const map = new Map<number, ModUpdate>();
    for (const u of updates) map.set(u.nexus_mod_id, u);
    return map;
  }, [updates]);

  const updateByInstalledId = useMemo(() => {
    const map = new Map<number, ModUpdate>();
    for (const u of updates) {
      if (u.installed_mod_id != null) map.set(u.installed_mod_id, u);
    }
    return map;
  }, [updates]);

  const installedNexusIds = useMemo(
    () => new Set(mods.filter((m) => m.nexus_mod_id != null).map((m) => m.nexus_mod_id!)),
    [mods],
  );

  const recognized = useMemo(
    () =>
      recognizedMods.filter(
        (m) => m.nexus_match && !installedNexusIds.has(m.nexus_match.nexus_mod_id),
      ),
    [recognizedMods, installedNexusIds],
  );

  const q = filter.toLowerCase();

  const filteredMods = useMemo(() => {
    let items = q ? mods.filter((m) => m.name.toLowerCase().includes(q)) : mods;

    if (chip === "enabled") {
      items = items.filter((m) => !m.disabled);
    } else if (chip === "disabled") {
      items = items.filter((m) => m.disabled);
    } else if (chip === "has-update") {
      items = items.filter(
        (m) =>
          updateByInstalledId.has(m.id) ||
          (m.nexus_mod_id != null && updateByNexusId.has(m.nexus_mod_id)),
      );
    }

    return items;
  }, [mods, q, chip, updateByInstalledId, updateByNexusId]);

  const filteredRecognized = useMemo(() => {
    const items = q
      ? recognized.filter(
          (m) =>
            m.display_name.toLowerCase().includes(q) ||
            (m.nexus_match?.mod_name.toLowerCase().includes(q) ?? false),
        )
      : [...recognized];

    items.sort((a, b) => {
      const ma = a.nexus_match;
      const mb = b.nexus_match;
      if (!ma || !mb) return 0;
      switch (recognizedSort) {
        case "name":
          return ma.mod_name.localeCompare(mb.mod_name);
        case "endorsements":
          return mb.endorsement_count - ma.endorsement_count;
        case "updated":
          return isoToEpoch(mb.updated_at) - isoToEpoch(ma.updated_at);
        case "confidence":
          return mb.score - ma.score;
      }
    });

    return items;
  }, [recognized, q, recognizedSort]);

  const totalCount = filteredMods.length + filteredRecognized.length;

  if (isLoading) {
    return <SkeletonTable columns={6} rows={5} />;
  }

  if (mods.length === 0 && recognized.length === 0) {
    return (
      <EmptyState
        icon={Package}
        title="No Installed Mods"
        description="Install mods from the Archives tab or run a scan to discover recognized mods."
        actions={
          onTabChange ? (
            <Button size="sm" variant="secondary" onClick={() => onTabChange("archives")}>
              Browse Archives
            </Button>
          ) : undefined
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="Filter by name..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="w-full rounded-lg border border-border bg-surface-2 py-1.5 pl-8 pr-3 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
          />
        </div>
        {recognized.length > 0 && (
          <SortSelect
            value={recognizedSort}
            onChange={(v) => setRecognizedSort(v as RecognizedSortKey)}
            options={RECOGNIZED_SORT_OPTIONS}
          />
        )}
        <span className="text-xs text-text-muted">
          {totalCount} mod{totalCount !== 1 ? "s" : ""}
        </span>
      </div>

      {filteredMods.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-text-primary" title="Mods installed and managed through this app — you can enable, disable, or uninstall them">
              Installed Mods ({filteredMods.length})
            </h3>
            <FilterChips
              chips={CHIP_OPTIONS}
              active={chip}
              onChange={(v) => setChip(v as ChipKey)}
            />
          </div>
          <ManagedModsTable
            mods={filteredMods}
            gameName={gameName}
            updateByInstalledId={updateByInstalledId}
            updateByNexusId={updateByNexusId}
            onModClick={onModClick}
          />
        </div>
      )}

      {filteredRecognized.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-text-primary mb-3" title="Mods found on disk and matched to Nexus — click Install to manage them">
            Detected on Disk ({filteredRecognized.length})
          </h3>
          <p className="text-xs text-text-muted mb-3">
            These mods were detected during scanning and matched to Nexus, but haven&apos;t been
            installed through the manager yet. Install them to enable features like profiles and updates.
          </p>
          <RecognizedModsGrid
            mods={filteredRecognized}
            archives={archives}
            installedModIds={installedNexusIds}
            gameName={gameName}
            downloadJobs={downloadJobs}
            updateByNexusId={updateByNexusId}
            onModClick={onModClick}
          />
        </div>
      )}

      {totalCount === 0 && (mods.length > 0 || recognized.length > 0) && (
        <p className="py-4 text-sm text-text-muted">
          No mods matching &quot;{filter}&quot;.
        </p>
      )}
    </div>
  );
}
