import { Download, Eye, Heart, RefreshCw, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { ModCardAction } from "@/components/mods/ModCardAction";
import { NexusModCard } from "@/components/mods/NexusModCard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useRefreshTrending } from "@/hooks/mutations";
import { useInstallFlow } from "@/hooks/use-install-flow";
import { formatCount } from "@/lib/format";
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

function timeAgo(timestamp: number): string {
  if (!timestamp) return "";
  const seconds = Math.floor(Date.now() / 1000 - timestamp);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

interface Props {
  mods: TrendingMod[];
  archives: AvailableArchive[];
  installedMods: InstalledModOut[];
  gameName: string;
  downloadJobs?: DownloadJobOut[];
}

export function TrendingGrid({
  mods,
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

  const filtered = useMemo(() => {
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
  }, [mods, filter, sortKey]);

  if (mods.length === 0) {
    return (
      <p className="text-text-muted text-sm py-4">
        No trending mods available. Try refreshing.
      </p>
    );
  }

  return (
    <div className="space-y-4">
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
          {filtered.length} mod{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((mod) => {
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
              nexusUrl={mod.nexus_url}
              footer={
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="inline-flex items-center gap-1 text-xs text-text-muted">
                    <Download size={11} />
                    {formatCount(mod.mod_downloads)}
                  </span>
                  {mod.updated_timestamp > 0 && (
                    <span className="text-xs text-text-muted">
                      {timeAgo(mod.updated_timestamp)}
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
    </div>
  );
}
