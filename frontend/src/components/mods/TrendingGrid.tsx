import { Clock, Copy, Download, ExternalLink, Eye, Heart, Info, RefreshCw, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { FomodWizard } from "@/components/mods/FomodWizard";
import { ModCardAction } from "@/components/mods/ModCardAction";
import { PreInstallPreview } from "@/components/mods/PreInstallPreview";
import { ModQuickActions } from "@/components/mods/ModQuickActions";
import { NexusModCard } from "@/components/mods/NexusModCard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ContextMenu, type ContextMenuItem } from "@/components/ui/ContextMenu";
import { OverflowMenuButton } from "@/components/ui/OverflowMenuButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { SearchInput } from "@/components/ui/SearchInput";
import { SkeletonCardGrid } from "@/components/ui/SkeletonCard";
import { SortSelect } from "@/components/ui/SortSelect";
import { VirtualCardGrid } from "@/components/ui/VirtualCardGrid";
import { useAbstainMod, useEndorseMod, useRefreshTrending, useTrackMod, useUntrackMod } from "@/hooks/mutations";
import { toast } from "@/stores/toast-store";
import { useContextMenu } from "@/hooks/use-context-menu";
import { useInstallFlow } from "@/hooks/use-install-flow";
import { useSessionState } from "@/hooks/use-session-state";
import { formatCount, timeAgo } from "@/lib/format";
import type { AvailableArchive, DownloadJobOut, InstalledModOut, TrendingMod } from "@/types/api";

type SortKey = "updated" | "downloads" | "endorsements" | "name";
type ChipKey = "all" | "installed" | "not-installed";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "updated", label: "Recently Updated" },
  { value: "downloads", label: "Downloads" },
  { value: "endorsements", label: "Endorsements" },
  { value: "name", label: "Name" },
];

const FILTER_CHIPS: { key: ChipKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "installed", label: "Installed" },
  { key: "not-installed", label: "Not Installed" },
];

function getContextMenuItems(mod: TrendingMod): ContextMenuItem[] {
  return [
    { key: "view", label: "View Details", icon: Info },
    { key: "nexus", label: "Open on Nexus", icon: ExternalLink },
    { key: "copy", label: "Copy Name", icon: Copy },
    { key: "sep-actions", label: "", separator: true },
    {
      key: "endorse",
      label: mod.is_endorsed ? "Remove Endorsement" : "Endorse",
      icon: Heart,
    },
    {
      key: "track",
      label: mod.is_tracked ? "Untrack" : "Track",
      icon: Eye,
    },
  ];
}

interface Props {
  trendingMods: TrendingMod[];
  latestUpdatedMods: TrendingMod[];
  archives: AvailableArchive[];
  installedMods: InstalledModOut[];
  gameName: string;
  downloadJobs?: DownloadJobOut[];
  isLoading?: boolean;
  dataUpdatedAt?: number;
  onModClick?: (nexusModId: number) => void;
  onFileSelect?: (nexusModId: number) => void;
}

export function TrendingGrid({
  trendingMods,
  latestUpdatedMods,
  archives,
  installedMods,
  gameName,
  downloadJobs = [],
  isLoading = false,
  dataUpdatedAt,
  onModClick,
  onFileSelect,
}: Props) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useSessionState<SortKey>(`trending-sort-${gameName}`, "updated");
  const [chip, setChip] = useSessionState<ChipKey>(`trending-chip-${gameName}`, "all");
  const [isStale, setIsStale] = useState(false);

  useEffect(() => {
    if (dataUpdatedAt == null) return;
    const check = () => setIsStale(Date.now() - dataUpdatedAt > 30 * 60 * 1000);
    check();
    const timer = setInterval(check, 60_000);
    return () => clearInterval(timer);
  }, [dataUpdatedAt]);

  const flow = useInstallFlow(gameName, archives, downloadJobs, onFileSelect);
  const refreshTrending = useRefreshTrending();
  const endorseMod = useEndorseMod();
  const abstainMod = useAbstainMod();
  const trackMod = useTrackMod();
  const untrackMod = useUntrackMod();
  const { menuState, openMenu, closeMenu } = useContextMenu<TrendingMod>();

  const installedModIds = useMemo(
    () =>
      new Set(
        installedMods
          .filter((m) => m.nexus_mod_id != null)
          .map((m) => m.nexus_mod_id!),
      ),
    [installedMods],
  );

  const filterAndSort = useCallback(
    (mods: TrendingMod[]) => {
      const q = filter.toLowerCase();
      let items = mods.filter((m) => {
        if (!q) return true;
        return m.name.toLowerCase().includes(q) || m.author.toLowerCase().includes(q);
      });

      if (chip === "installed") {
        items = items.filter((m) => m.is_installed || installedModIds.has(m.mod_id));
      } else if (chip === "not-installed") {
        items = items.filter((m) => !m.is_installed && !installedModIds.has(m.mod_id));
      }

      items.sort((a, b) => {
        switch (sortKey) {
          case "updated":
            return b.updated_timestamp - a.updated_timestamp;
          case "downloads":
            return b.mod_downloads - a.mod_downloads;
          case "endorsements":
            return b.endorsement_count - a.endorsement_count;
          case "name":
            return a.name.localeCompare(b.name);
        }
      });

      return items;
    },
    [filter, sortKey, chip, installedModIds],
  );

  const filteredTrending = useMemo(
    () => filterAndSort(trendingMods),
    [trendingMods, filterAndSort],
  );
  const filteredLatest = useMemo(
    () => filterAndSort(latestUpdatedMods),
    [latestUpdatedMods, filterAndSort],
  );

  const totalCount = filteredTrending.length + filteredLatest.length;

  const handleContextMenuSelect = (key: string) => {
    const mod = menuState.data;
    if (!mod) return;
    if (key === "view") onModClick?.(mod.mod_id);
    else if (key === "nexus") window.open(mod.nexus_url, "_blank", "noopener,noreferrer");
    else if (key === "copy") void navigator.clipboard.writeText(mod.name).then(
      () => toast.success("Copied to clipboard"),
      () => toast.error("Failed to copy"),
    );
    else if (key === "endorse") {
      if (mod.is_endorsed) abstainMod.mutate({ gameName, modId: mod.mod_id });
      else endorseMod.mutate({ gameName, modId: mod.mod_id });
    } else if (key === "track") {
      if (mod.is_tracked) untrackMod.mutate({ gameName, modId: mod.mod_id });
      else trackMod.mutate({ gameName, modId: mod.mod_id });
    }
  };

  const renderModCard = (mod: TrendingMod) => {
    const nexusModId = mod.mod_id;
    const archive = flow.archiveByModId.get(nexusModId);
    const dl = flow.completedDownloadByModId.get(nexusModId);
    const isInstalled = mod.is_installed || installedModIds.has(nexusModId);

    return (
      <NexusModCard
        key={nexusModId}
        modName={mod.name}
        summary={mod.summary}
        author={mod.author}
        version={mod.version}
        endorsementCount={mod.endorsement_count}
        pictureUrl={mod.picture_url}
        onClick={() => onModClick?.(nexusModId)}
        onContextMenu={(e) => openMenu(e, mod)}
        badge={
          mod.is_tracked ? (
            <Badge variant="neutral">
              <Eye size={10} className="mr-0.5" /> Tracked
            </Badge>
          ) : undefined
        }
        footer={
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs text-text-muted">
              <Download size={11} />
              {formatCount(mod.mod_downloads)}
            </span>
            {mod.category_name && (
              <Badge variant="neutral">{mod.category_name}</Badge>
            )}
            {mod.updated_timestamp > 0 && (
              <span className="text-xs text-text-muted">{timeAgo(mod.updated_timestamp)}</span>
            )}
            <ModQuickActions
              isEndorsed={mod.is_endorsed}
              isTracked={mod.is_tracked}
              modId={nexusModId}
              gameName={gameName}
            />
          </div>
        }
        action={
          <ModCardAction
            isInstalled={isInstalled}
            isInstalling={flow.installingModIds.has(nexusModId)}
            activeDownload={flow.activeDownloadByModId.get(nexusModId)}
            completedDownload={flow.completedDownloadByModId.get(nexusModId)}
            archive={archive}
            nexusUrl={mod.nexus_url}
            hasConflicts={flow.conflicts != null}
            isDownloading={flow.downloadingModId === nexusModId}
            onInstall={() => archive && flow.handleInstall(nexusModId, archive)}
            onInstallByFilename={() => {
              if (dl) flow.handleInstallByFilename(nexusModId, dl.file_name);
            }}
            onDownload={() => flow.handleDownload(nexusModId)}
            onCancelDownload={() => {
              const dl = flow.activeDownloadByModId.get(nexusModId);
              if (dl) flow.handleCancelDownload(dl.id);
            }}
            onInstallWithPreview={
              dl
                ? () => flow.handleInstallWithPreviewByFilename(nexusModId, dl.file_name)
                : archive
                  ? () => flow.handleInstallWithPreview(nexusModId, archive)
                  : undefined
            }
          />
        }
        overflowMenu={
          <OverflowMenuButton
            items={getContextMenuItems(mod)}
            onSelect={(key) => {
              if (key === "view") onModClick?.(nexusModId);
              else if (key === "nexus") window.open(mod.nexus_url, "_blank", "noopener,noreferrer");
              else if (key === "copy") void navigator.clipboard.writeText(mod.name).then(
                () => toast.success("Copied to clipboard"),
                () => toast.error("Failed to copy"),
              );
              else if (key === "endorse") {
                if (mod.is_endorsed) abstainMod.mutate({ gameName, modId: nexusModId });
                else endorseMod.mutate({ gameName, modId: nexusModId });
              } else if (key === "track") {
                if (mod.is_tracked) untrackMod.mutate({ gameName, modId: nexusModId });
                else trackMod.mutate({ gameName, modId: nexusModId });
              }
            }}
          />
        }
      />
    );
  };

  // Show skeleton grid while initial data is being fetched.
  if (isLoading) {
    return <SkeletonCardGrid count={6} />;
  }

  // Show empty state when there is no data and no active filter hiding results.
  if (trendingMods.length === 0 && latestUpdatedMods.length === 0) {
    return (
      <EmptyState
        icon={TrendingUp}
        title="No Trending Data"
        description="Refresh to fetch the latest trending mods from Nexus."
        actions={
          <Button
            size="sm"
            onClick={() => refreshTrending.mutate(gameName)}
            loading={refreshTrending.isPending}
          >
            Refresh
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Toolbar: search, sort, filter chips, refresh, and count */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <SearchInput value={filter} onChange={setFilter} placeholder="Filter by name or author..." />
          <SortSelect
            value={sortKey}
            onChange={(v) => setSortKey(v as SortKey)}
            options={SORT_OPTIONS}
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refreshTrending.mutate(gameName)}
            loading={refreshTrending.isPending}
          >
            <RefreshCw className="h-3.5 w-3.5 mr-1" />
            Refresh
          </Button>
          <span className="text-xs text-text-muted">
            {totalCount} mod{totalCount !== 1 ? "s" : ""}
          </span>
          {isStale && dataUpdatedAt != null && (
            <span className="text-xs text-warning" title="Data may be outdated — click Refresh to update">
              Updated {timeAgo(Math.floor(dataUpdatedAt / 1000))}
            </span>
          )}
        </div>
        <FilterChips
          chips={FILTER_CHIPS}
          active={chip}
          onChange={(key) => setChip(key as ChipKey)}
        />
      </div>

      {filteredTrending.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <TrendingUp size={16} className="text-accent" />
            <h3 className="text-sm font-semibold text-text-primary">Trending</h3>
            <span className="text-xs text-text-muted">
              {filteredTrending.length} mod{filteredTrending.length !== 1 ? "s" : ""}
            </span>
          </div>
          <VirtualCardGrid items={filteredTrending} renderItem={renderModCard} />
        </div>
      )}

      {filteredLatest.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Clock size={16} className="text-warning" />
            <h3 className="text-sm font-semibold text-text-primary">Recently Updated</h3>
            <span className="text-xs text-text-muted">
              {filteredLatest.length} mod{filteredLatest.length !== 1 ? "s" : ""}
            </span>
          </div>
          <VirtualCardGrid items={filteredLatest} renderItem={renderModCard} />
        </div>
      )}

      {/* Filtered empty state shown when data exists but active filters match nothing. */}
      {filteredTrending.length === 0 && filteredLatest.length === 0 && (
        <EmptyState
          icon={TrendingUp}
          title="No Trending Data"
          description="No mods match the current filter. Try changing the filter or search term."
        />
      )}

      {flow.previewArchive && (
        <PreInstallPreview
          gameName={gameName}
          archiveFilename={flow.previewArchive.filename}
          onConfirm={(renames) => flow.confirmPreviewInstall(renames)}
          onCancel={flow.dismissPreview}
        />
      )}

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

      {/* Context menu rendered at document level to avoid clipping. */}
      {menuState.visible && menuState.data && (
        <ContextMenu
          items={getContextMenuItems(menuState.data)}
          position={menuState.position}
          onSelect={handleContextMenuSelect}
          onClose={closeMenu}
        />
      )}
    </div>
  );
}
