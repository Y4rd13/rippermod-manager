import { Check, Clock, Copy, Download, ExternalLink, Eye, Heart, Info, RefreshCw, Search, TrendingUp } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { ModCardAction } from "@/components/mods/ModCardAction";
import { NexusModCard } from "@/components/mods/NexusModCard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ContextMenu, type ContextMenuItem } from "@/components/ui/ContextMenu";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { SkeletonCardGrid } from "@/components/ui/SkeletonCard";
import { SortSelect } from "@/components/ui/SortSelect";
import { useRefreshTrending } from "@/hooks/mutations";
import { useContextMenu } from "@/hooks/use-context-menu";
import { useInstallFlow } from "@/hooks/use-install-flow";
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

const CONTEXT_MENU_ITEMS: ContextMenuItem[] = [
  { key: "view", label: "View Details", icon: Info },
  { key: "nexus", label: "Open on Nexus", icon: ExternalLink },
  { key: "copy", label: "Copy Name", icon: Copy },
];

interface Props {
  trendingMods: TrendingMod[];
  latestUpdatedMods: TrendingMod[];
  archives: AvailableArchive[];
  installedMods: InstalledModOut[];
  gameName: string;
  downloadJobs?: DownloadJobOut[];
  isLoading?: boolean;
  onModClick?: (nexusModId: number) => void;
}

export function TrendingGrid({
  trendingMods,
  latestUpdatedMods,
  archives,
  installedMods,
  gameName,
  downloadJobs = [],
  isLoading = false,
  onModClick,
}: Props) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("updated");
  const [chip, setChip] = useState<ChipKey>("all");

  const flow = useInstallFlow(gameName, archives, downloadJobs);
  const refreshTrending = useRefreshTrending();
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
    else if (key === "copy") navigator.clipboard.writeText(mod.name);
  };

  const renderModCard = (mod: TrendingMod) => {
    const nexusModId = mod.mod_id;
    const archive = flow.archiveByModId.get(nexusModId);
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
          <div className="flex items-center gap-1">
            {isInstalled && (
              <Badge variant="success">
                <Check size={10} className="mr-0.5" />
                Installed
              </Badge>
            )}
            {mod.is_tracked && (
              <Badge variant="neutral">
                <Eye size={10} className="mr-0.5" /> Tracked
              </Badge>
            )}
            {mod.is_endorsed && (
              <Badge variant="success">
                <Heart size={10} className="mr-0.5" /> Endorsed
              </Badge>
            )}
          </div>
        }
        footer={
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs text-text-muted">
              <Download size={11} />
              {formatCount(mod.mod_downloads)}
            </span>
            {mod.updated_timestamp > 0 && (
              <span className="text-xs text-text-muted">{timeAgo(mod.updated_timestamp)}</span>
            )}
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
              const dl = flow.completedDownloadByModId.get(nexusModId);
              if (dl) flow.handleInstallByFilename(nexusModId, dl.file_name);
            }}
            onDownload={() => flow.handleDownload(nexusModId)}
            onCancelDownload={() => {
              const dl = flow.activeDownloadByModId.get(nexusModId);
              if (dl) flow.handleCancelDownload(dl.id);
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
          <div className="relative flex-1 max-w-xs">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted"
            />
            <input
              type="text"
              placeholder="Filter by name or author..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-full rounded-lg border border-border bg-surface-2 py-1.5 pl-8 pr-3 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
            />
          </div>
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
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredTrending.map(renderModCard)}
          </div>
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
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredLatest.map(renderModCard)}
          </div>
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

      {flow.conflicts && (
        <ConflictDialog
          conflicts={flow.conflicts}
          onCancel={flow.dismissConflicts}
          onSkip={flow.handleInstallWithSkip}
          onOverwrite={flow.handleInstallOverwrite}
        />
      )}

      {/* Context menu rendered at document level to avoid clipping. */}
      {menuState.visible && (
        <ContextMenu
          items={CONTEXT_MENU_ITEMS}
          position={menuState.position}
          onSelect={handleContextMenuSelect}
          onClose={closeMenu}
        />
      )}
    </div>
  );
}
