import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { ModCardAction } from "@/components/mods/ModCardAction";
import { NexusModCard } from "@/components/mods/NexusModCard";
import { useInstallFlow } from "@/hooks/use-install-flow";
import type {
  AvailableArchive,
  DownloadJobOut,
  InstalledModOut,
  NexusDownload,
} from "@/types/api";

type SortKey = "name" | "endorsements" | "author";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "name", label: "Mod Name" },
  { value: "endorsements", label: "Endorsements" },
  { value: "author", label: "Author" },
];

interface Props {
  mods: NexusDownload[];
  archives: AvailableArchive[];
  installedMods: InstalledModOut[];
  gameName: string;
  emptyMessage: string;
  downloadJobs?: DownloadJobOut[];
}

export function NexusAccountGrid({
  mods,
  archives,
  installedMods,
  gameName,
  emptyMessage,
  downloadJobs = [],
}: Props) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("name");

  const flow = useInstallFlow(gameName, archives, downloadJobs);

  const installedModIds = useMemo(
    () => new Set(installedMods.filter((m) => m.nexus_mod_id != null).map((m) => m.nexus_mod_id!)),
    [installedMods],
  );

  const filtered = useMemo(() => {
    const q = filter.toLowerCase();
    const items = mods.filter((m) => {
      if (!q) return true;
      return (
        m.mod_name.toLowerCase().includes(q) ||
        m.author.toLowerCase().includes(q)
      );
    });

    items.sort((a, b) => {
      switch (sortKey) {
        case "name":
          return a.mod_name.localeCompare(b.mod_name);
        case "endorsements":
          return b.endorsement_count - a.endorsement_count;
        case "author":
          return a.author.localeCompare(b.author);
      }
    });

    return items;
  }, [mods, filter, sortKey]);

  if (mods.length === 0) {
    return (
      <p className="text-text-muted text-sm py-4">{emptyMessage}</p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
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
        <span className="text-xs text-text-muted">
          {filtered.length} mod{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((mod) => {
          const nexusModId = mod.nexus_mod_id;
          const archive = flow.archiveByModId.get(nexusModId);

          return (
            <NexusModCard
              key={mod.id}
              modName={mod.mod_name}
              summary={mod.summary}
              author={mod.author}
              version={mod.version}
              endorsementCount={mod.endorsement_count}
              pictureUrl={mod.picture_url}
              nexusUrl={mod.nexus_url}
              action={
                <ModCardAction
                  nexusModId={nexusModId}
                  isInstalled={installedModIds.has(nexusModId)}
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
