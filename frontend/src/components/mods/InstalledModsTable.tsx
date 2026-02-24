import {
  ArrowUp,
  Copy,
  ExternalLink,
  Package,
  Power,
  PowerOff,
  Trash2,
} from "lucide-react";
import { useMemo, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";

import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { FomodWizard } from "@/components/mods/FomodWizard";
import { CorrelationActions } from "@/components/mods/CorrelationActions";
import { InstalledModCardAction } from "@/components/mods/InstalledModCardAction";
import { ModCardAction } from "@/components/mods/ModCardAction";
import { NexusModCard } from "@/components/mods/NexusModCard";
import { Badge, ConfidenceBadge } from "@/components/ui/Badge";
import { BulkActionBar } from "@/components/ui/BulkActionBar";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ContextMenu, type ContextMenuItem } from "@/components/ui/ContextMenu";
import { OverflowMenuButton } from "@/components/ui/OverflowMenuButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { SearchInput } from "@/components/ui/SearchInput";
import { SkeletonCardGrid } from "@/components/ui/SkeletonCard";
import { SortSelect } from "@/components/ui/SortSelect";
import { VirtualCardGrid } from "@/components/ui/VirtualCardGrid";
import { useBulkSelect } from "@/hooks/use-bulk-select";
import { useContextMenu } from "@/hooks/use-context-menu";
import { useSessionState } from "@/hooks/use-session-state";
import { useToggleMod, useUninstallMod } from "@/hooks/mutations";
import { useInstallFlow } from "@/hooks/use-install-flow";
import { isoToEpoch, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { toast } from "@/stores/toast-store";
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

type ScopeKey = "all" | "installed" | "detected";

type ChipKey = "all" | "enabled" | "disabled" | "has-update";

const SCOPE_OPTIONS: { key: ScopeKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "installed", label: "Installed" },
  { key: "detected", label: "Detected on Disk" },
];

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

const MANAGED_SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "updated", label: "Recently Updated" },
  { value: "name", label: "Mod Name" },
  { value: "disabled", label: "Status" },
  { value: "version", label: "Version" },
  { value: "files", label: "File Count" },
];

function ManagedModsGrid({
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
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmDeleteModId, setConfirmDeleteModId] = useState<number | null>(null);
  const toggleMod = useToggleMod();
  const uninstallMod = useUninstallMod();

  const sorted = useMemo(
    () =>
      [...mods].sort((a, b) => {
        switch (sortKey) {
          case "name":
            return (a.nexus_name || a.name).localeCompare(b.nexus_name || b.name);
          case "version":
            return a.installed_version.localeCompare(b.installed_version);
          case "files":
            return b.file_count - a.file_count;
          case "disabled":
            return Number(a.disabled) - Number(b.disabled);
          case "updated":
            return isoToEpoch(b.nexus_updated_at) - isoToEpoch(a.nexus_updated_at);
          default:
            return 0;
        }
      }),
    [mods, sortKey],
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
        void navigator.clipboard.writeText(mod.nexus_name || mod.name).then(
          () => toast.success("Copied to clipboard"),
          () => toast.error("Failed to copy"),
        );
        break;
      case "delete":
        setConfirmDeleteModId(mod.id);
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
    setConfirmDelete(false);
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
  const confirmDeleteMod = confirmDeleteModId != null
    ? sorted.find((m) => m.id === confirmDeleteModId)
    : null;

  return (
    <>
      <div className="flex items-center justify-between mb-3">
        <SortSelect
          value={sortKey}
          onChange={(v) => setSortKey(v as SortKey)}
          options={MANAGED_SORT_OPTIONS}
        />
      </div>

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
        <Button size="sm" variant="danger" onClick={() => setConfirmDelete(true)}>
          <Trash2 size={12} className="mr-1" /> Delete
        </Button>
      </BulkActionBar>

      <VirtualCardGrid
        items={sorted}
        renderItem={(mod) => {
          const update =
            updateByInstalledId.get(mod.id) ??
            (mod.nexus_mod_id ? updateByNexusId.get(mod.nexus_mod_id) : undefined);
          return (
            <div className={cn("relative grid", mod.disabled && "opacity-60")}>
              <div className="absolute top-2 left-2 z-10">
                <input
                  type="checkbox"
                  checked={bulk.isSelected(mod.id)}
                  onChange={() => bulk.toggle(mod.id)}
                  onClick={(e) => e.stopPropagation()}
                  className="shrink-0"
                />
              </div>
              <NexusModCard
                modName={mod.nexus_name || mod.name}
                summary={mod.summary ?? undefined}
                author={mod.author ?? undefined}
                version={mod.installed_version || undefined}
                endorsementCount={mod.endorsement_count ?? undefined}
                pictureUrl={mod.picture_url ?? undefined}
                badge={
                  update ? (
                    <span title={update.reason || `Update: v${update.local_version} → v${update.nexus_version}`}>
                      <Badge variant="warning" prominent>
                        <ArrowUp size={10} className="mr-0.5" />
                        v{update.nexus_version}
                      </Badge>
                    </span>
                  ) : undefined
                }
                footer={
                  <div className="flex items-center gap-1.5">
                    <Badge variant={mod.disabled ? "danger" : "success"}>
                      {mod.disabled ? (
                        <><PowerOff size={10} className="mr-0.5" /> Disabled</>
                      ) : (
                        <><Power size={10} className="mr-0.5" /> Enabled</>
                      )}
                    </Badge>
                    {mod.nexus_updated_at && (
                      <span className="text-xs text-text-muted">
                        {timeAgo(isoToEpoch(mod.nexus_updated_at))}
                      </span>
                    )}
                    {mod.last_downloaded_at && (
                      <span className="text-xs text-text-muted" title="Last downloaded">
                        DL: {timeAgo(isoToEpoch(mod.last_downloaded_at))}
                      </span>
                    )}
                    {mod.nexus_url && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          openUrl(mod.nexus_url!).catch(() => {});
                        }}
                        title="Open mod page on Nexus Mods"
                        aria-label="Open on Nexus Mods"
                        className="ml-auto rounded p-1 text-text-muted hover:text-accent hover:bg-accent/10 shrink-0 transition-colors"
                      >
                        <ExternalLink size={12} />
                      </button>
                    )}
                  </div>
                }
                action={
                  <InstalledModCardAction
                    disabled={mod.disabled}
                    isToggling={toggleMod.isPending && toggleMod.variables?.modId === mod.id}
                    isUninstalling={uninstallMod.isPending && uninstallMod.variables?.modId === mod.id}
                    onToggle={() => toggleMod.mutateAsync({ gameName, modId: mod.id })}
                    onUninstall={() => uninstallMod.mutateAsync({ gameName, modId: mod.id })}
                  />
                }
                overflowMenu={
                  <OverflowMenuButton
                    items={buildContextMenuItems(mod)}
                    onSelect={(key) => {
                      switch (key) {
                        case "enable":
                        case "disable":
                          toggleMod.mutate({ gameName, modId: mod.id });
                          break;
                        case "nexus":
                          if (mod.nexus_mod_id) onModClick?.(mod.nexus_mod_id);
                          break;
                        case "copy":
                          void navigator.clipboard.writeText(mod.nexus_name || mod.name).then(
                            () => toast.success("Copied to clipboard"),
                            () => toast.error("Failed to copy"),
                          );
                          break;
                        case "delete":
                          setConfirmDeleteModId(mod.id);
                          break;
                      }
                    }}
                  />
                }
                onClick={mod.nexus_mod_id ? () => onModClick?.(mod.nexus_mod_id!) : undefined}
                onContextMenu={(e) => openMenu(e, mod)}
              />
            </div>
          );
        }}
      />

      {menuState.visible && menuState.data && (
        <ContextMenu
          items={buildContextMenuItems(menuState.data)}
          position={menuState.position}
          onSelect={handleContextMenuSelect}
          onClose={closeMenu}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Delete Selected Mods"
          message={`This will permanently delete ${bulk.selectedCount} mod${bulk.selectedCount !== 1 ? "s" : ""} and their files. This action cannot be undone.`}
          confirmLabel="Delete"
          variant="danger"
          icon={Trash2}
          onConfirm={handleBulkDelete}
          onCancel={() => setConfirmDelete(false)}
        />
      )}

      {confirmDeleteMod && (
        <ConfirmDialog
          title="Delete Mod?"
          message={`Permanently delete "${confirmDeleteMod.nexus_name || confirmDeleteMod.name}" and its files? This cannot be undone.`}
          confirmLabel="Delete"
          variant="danger"
          icon={Trash2}
          loading={uninstallMod.isPending}
          onConfirm={async () => {
            await uninstallMod.mutateAsync({ gameName, modId: confirmDeleteMod.id });
            setConfirmDeleteModId(null);
          }}
          onCancel={() => setConfirmDeleteModId(null)}
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

  const modIds = useMemo(() => mods.map((m) => String(m.id)), [mods]);
  const bulk = useBulkSelect(modIds);

  const handleBulkInstall = async () => {
    for (const modIdStr of bulk.selectedIds) {
      const mod = mods.find((m) => String(m.id) === modIdStr);
      const nexusModId = mod?.nexus_match?.nexus_mod_id;
      if (nexusModId == null) continue;
      const archive = flow.archiveByModId.get(nexusModId);
      if (archive) {
        try {
          await flow.handleInstall(nexusModId, archive);
        } catch {
          // Continue with remaining mods on individual failure
        }
      }
    }
    bulk.deselectAll();
  };

  return (
    <>
      <VirtualCardGrid
        items={mods}
        renderItem={(mod) => {
          const match = mod.nexus_match;
          if (!match) return null;

          const nexusModId = match.nexus_mod_id;
          const archive = nexusModId != null ? flow.archiveByModId.get(nexusModId) : undefined;
          const update = nexusModId != null ? updateByNexusId.get(nexusModId) : undefined;

          return (
            <div className="relative grid">
              <div className="absolute top-2 left-2 z-10">
                <input
                  type="checkbox"
                  checked={bulk.isSelected(String(mod.id))}
                  onChange={() => bulk.toggle(String(mod.id))}
                  className="shrink-0"
                />
              </div>
              <NexusModCard
                modName={match.mod_name}
                summary={match.summary}
                author={match.author}
                version={match.version}
                endorsementCount={match.endorsement_count}
                pictureUrl={match.picture_url}
                badge={update ? <Badge variant="warning" prominent><ArrowUp size={10} className="mr-0.5" />v{update.nexus_version} available</Badge> : undefined}
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
                    <CorrelationActions
                      gameName={gameName}
                      modGroupId={mod.id}
                      confirmed={match.confirmed}
                    />
                    {match.updated_at && (
                      <span className="text-xs text-text-muted">{timeAgo(isoToEpoch(match.updated_at))}</span>
                    )}
                  </div>
                }
              />
            </div>
          );
        }}
      />

      <BulkActionBar
        selectedCount={bulk.selectedCount}
        totalCount={mods.length}
        onSelectAll={bulk.selectAll}
        onDeselectAll={bulk.deselectAll}
        isAllSelected={bulk.isAllSelected}
      >
        <Button size="sm" onClick={handleBulkInstall}>
          Install {bulk.selectedCount} Selected
        </Button>
      </BulkActionBar>

      {flow.fomodArchive && (
        <FomodWizard gameName={gameName} archiveFilename={flow.fomodArchive} onDismiss={flow.dismissFomod} onInstallComplete={flow.dismissFomod} />
      )}

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
  const [chip, setChip] = useSessionState<ChipKey>(`installed-chip-${gameName}`, "all");
  const [scope, setScope] = useSessionState<ScopeKey>(`installed-scope-${gameName}`, "all");
  const [recognizedSort, setRecognizedSort] = useSessionState<RecognizedSortKey>(`installed-recsort-${gameName}`, "updated");

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
    let items = q
      ? mods.filter(
          (m) =>
            m.name.toLowerCase().includes(q) ||
            (m.nexus_name?.toLowerCase().includes(q) ?? false),
        )
      : mods;

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

  const totalCount =
    (scope !== "detected" ? filteredMods.length : 0) +
    (scope !== "installed" ? filteredRecognized.length : 0);

  if (isLoading) {
    return <SkeletonCardGrid count={6} />;
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
        <SearchInput value={filter} onChange={setFilter} placeholder="Filter by name..." />
        {recognized.length > 0 && (
          <SortSelect
            value={recognizedSort}
            onChange={(v) => setRecognizedSort(v as RecognizedSortKey)}
            options={RECOGNIZED_SORT_OPTIONS}
          />
        )}
        {mods.length > 0 && recognized.length > 0 && (
          <FilterChips
            chips={SCOPE_OPTIONS}
            active={scope}
            onChange={(v) => setScope(v as ScopeKey)}
          />
        )}
        <span className="text-xs text-text-muted">
          {totalCount} mod{totalCount !== 1 ? "s" : ""}
        </span>
      </div>

      {mods.length > 0 && scope !== "detected" && (
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
          {filteredMods.length > 0 ? (
            <ManagedModsGrid
              mods={filteredMods}
              gameName={gameName}
              updateByInstalledId={updateByInstalledId}
              updateByNexusId={updateByNexusId}
              onModClick={onModClick}
            />
          ) : (
            <p className="py-4 text-sm text-text-muted text-center">
              No {chip === "disabled" ? "disabled" : chip === "enabled" ? "enabled" : "updatable"} mods.
            </p>
          )}
        </div>
      )}

      {filteredRecognized.length > 0 && scope !== "installed" && (
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

      {totalCount === 0 && (filter || scope !== "all") && (mods.length > 0 || recognized.length > 0) && (
        <p className="py-4 text-sm text-text-muted text-center">
          {filter ? <>No mods matching &quot;{filter}&quot;.</> : "No mods in this view."}
        </p>
      )}
    </div>
  );
}
