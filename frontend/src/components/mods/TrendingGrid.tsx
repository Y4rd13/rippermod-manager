import { Calendar, Clock, Download, Eye, Heart, RefreshCw, Search, TrendingUp, Users } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { ModCardAction } from "@/components/mods/ModCardAction";
import { NexusModCard } from "@/components/mods/NexusModCard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useRefreshTrending } from "@/hooks/mutations";
import { useInstallFlow } from "@/hooks/use-install-flow";
import { formatCount, timeAgo } from "@/lib/format";
import type {
  AvailableArchive,
  DownloadJobOut,
  InstalledModOut,
  TrendingMod,
} from "@/types/api";

type SortKey = "updated" | "downloads" | "endorsements" | "name";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "updated", label: "Recently Updated" },
  { value: "downloads", label: "Downloads" },
  { value: "endorsements", label: "Endorsements" },
  { value: "name", label: "Name" },
];

interface Props {
  trendingMods: TrendingMod[];
  latestUpdatedMods: TrendingMod[];
  archives: AvailableArchive[];
  installedMods: InstalledModOut[];
  gameName: string;
  downloadJobs?: DownloadJobOut[];
}

export function TrendingGrid({
  trendingMods,
  latestUpdatedMods,
  archives,
  installedMods,
  gameName,
  downloadJobs = [],
}: Props) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("updated");

  const flow = useInstallFlow(gameName, archives, downloadJobs);
  const refreshTrending = useRefreshTrending();

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
      const items = mods.filter((m) => {
        if (!q) return true;
        return (
          m.name.toLowerCase().includes(q) ||
          m.author.toLowerCase().includes(q)
        );
      });

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
    [filter, sortKey],
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

  const renderModCard = (mod: TrendingMod) => {
    const nexusModId = mod.mod_id;
    const archive = flow.archiveByModId.get(nexusModId);
    const isInstalled =
      mod.is_installed || installedModIds.has(nexusModId);

    return (
      <NexusModCard
        key={nexusModId}
        modName={mod.name}
        summary={mod.summary}
        author={mod.author}
        version={mod.version}
        endorsementCount={mod.endorsement_count}
        pictureUrl={mod.picture_url}
        footer={
          <div className="flex items-center gap-2 flex-wrap">
            <span className="inline-flex items-center gap-1 text-xs text-text-muted">
              <Download size={11} />
              {formatCount(mod.mod_downloads)}
            </span>
            {mod.mod_unique_downloads > 0 && (
              <span className="inline-flex items-center gap-1 text-xs text-text-muted" title="Unique downloads">
                <Users size={11} />
                {formatCount(mod.mod_unique_downloads)}
              </span>
            )}
            {mod.updated_timestamp > 0 && (
              <span className="text-xs text-text-muted">
                {timeAgo(mod.updated_timestamp)}
              </span>
            )}
            {mod.created_timestamp > 0 && (
              <span className="inline-flex items-center gap-0.5 text-xs text-text-muted">
                <Calendar size={10} />
                {timeAgo(mod.created_timestamp)}
              </span>
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
        action={
          <ModCardAction
            isInstalled={isInstalled}
            isInstalling={flow.installingModIds.has(nexusModId)}
            activeDownload={flow.activeDownloadByModId.get(nexusModId)}
            completedDownload={flow.completedDownloadByModId.get(
              nexusModId,
            )}
            archive={archive}
            nexusUrl={mod.nexus_url}
            hasConflicts={flow.conflicts != null}
            isDownloading={flow.downloadingModId === nexusModId}
            onInstall={() =>
              archive && flow.handleInstall(nexusModId, archive)
            }
            onInstallByFilename={() => {
              const dl =
                flow.completedDownloadByModId.get(nexusModId);
              if (dl)
                flow.handleInstallByFilename(nexusModId, dl.file_name);
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

  if (trendingMods.length === 0 && latestUpdatedMods.length === 0) {
    return (
      <p className="text-text-muted text-sm py-4">
        No trending mods available. Try refreshing.
      </p>
    );
  }

  return (
    <div className="space-y-6">
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
        <select
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
          className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
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

      {flow.conflicts && (
        <ConflictDialog
          conflicts={flow.conflicts}
          onCancel={flow.dismissConflicts}
          onSkip={flow.handleInstallWithSkip}
          onOverwrite={flow.handleInstallOverwrite}
        />
      )}
    </div>
  );
}
