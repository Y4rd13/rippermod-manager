import {
  ArrowUp,
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
import { Button } from "@/components/ui/Button";
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
  onModClick?: (nexusModId: number) => void;
}

type SortKey = "name" | "version" | "files" | "disabled" | "updated";

type RecognizedSortKey = "name" | "endorsements" | "updated" | "confidence";

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
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
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

  const sorted = [...mods].sort((a, b) => {
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
  });

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-text-muted">
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
                className="cursor-pointer select-none pb-2 pr-4 hover:text-text-primary"
                onClick={() => handleSort(key)}
              >
                {label} {sortKey === key && (sortDir === "asc" ? "^" : "v")}
              </th>
            ))}
            <th className="pb-2 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((mod) => {
            const update = updateByInstalledId.get(mod.id)
              ?? (mod.nexus_mod_id ? updateByNexusId.get(mod.nexus_mod_id) : undefined);
            return (
            <tr
              key={mod.id}
              className={cn(
                "border-b border-border/50",
                mod.disabled && "opacity-50",
                update && !mod.disabled && "bg-warning/5",
              )}
            >
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
                  <span className="ml-2 text-xs text-text-muted">
                    #{mod.nexus_mod_id}
                  </span>
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
                {mod.nexus_updated_at
                  ? timeAgo(isoToEpoch(mod.nexus_updated_at))
                  : "—"}
              </td>
              <td className="py-2 text-right">
                <div className="flex items-center justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={
                      toggleMod.isPending &&
                      toggleMod.variables?.modId === mod.id
                    }
                    onClick={() =>
                      toggleMod.mutate({ gameName, modId: mod.id })
                    }
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
                        uninstallMod.isPending &&
                        uninstallMod.variables?.modId === mod.id
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
  onModClick,
}: Props) {
  const [filter, setFilter] = useState("");
  const [recognizedSort, setRecognizedSort] = useState<RecognizedSortKey>("confidence");

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
    if (!q) return mods;
    return mods.filter((m) => m.name.toLowerCase().includes(q));
  }, [mods, q]);

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

  if (mods.length === 0 && recognized.length === 0) {
    return (
      <p className="py-4 text-sm text-text-muted">
        No installed mods. Install mods from the Archives tab or run a scan to discover recognized
        mods.
      </p>
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
          <select
            value={recognizedSort}
            onChange={(e) => setRecognizedSort(e.target.value as RecognizedSortKey)}
            className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
          >
            {RECOGNIZED_SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        )}
        <span className="text-xs text-text-muted">
          {totalCount} mod{totalCount !== 1 ? "s" : ""}
        </span>
      </div>

      {filteredMods.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-text-primary mb-3">
            Managed Mods ({filteredMods.length})
          </h3>
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
          <h3 className="text-sm font-semibold text-text-primary mb-3">
            Recognized Mods ({filteredRecognized.length})
          </h3>
          <p className="text-xs text-text-muted mb-3">
            These mods were detected during scanning and matched to Nexus, but haven&apos;t been
            formally installed through the manager yet.
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
