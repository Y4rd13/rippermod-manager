import {
  Power,
  PowerOff,
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
import type { AvailableArchive, DownloadJobOut, InstalledModOut, ModGroup } from "@/types/api";

interface Props {
  mods: InstalledModOut[];
  gameName: string;
  recognizedMods?: ModGroup[];
  archives?: AvailableArchive[];
  downloadJobs?: DownloadJobOut[];
}

type SortKey = "name" | "version" | "files" | "disabled" | "updated";

function ManagedModsTable({
  mods,
  gameName,
}: {
  mods: InstalledModOut[];
  gameName: string;
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
          {sorted.map((mod) => (
            <tr
              key={mod.id}
              className={cn(
                "border-b border-border/50",
                mod.disabled && "opacity-50",
              )}
            >
              <td className="py-2 pr-4">
                <span className="text-text-primary">{mod.name}</span>
                {mod.nexus_mod_id && (
                  <span className="ml-2 text-xs text-text-muted">
                    #{mod.nexus_mod_id}
                  </span>
                )}
              </td>
              <td className="py-2 pr-4 text-text-muted">
                {mod.installed_version || "--"}
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
          ))}
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
}: {
  mods: ModGroup[];
  archives: AvailableArchive[];
  installedModIds: Set<number>;
  gameName: string;
  downloadJobs: DownloadJobOut[];
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

          return (
            <NexusModCard
              key={mod.id}
              modName={match.mod_name}
              summary={match.summary}
              author={match.author}
              version={match.version}
              endorsementCount={match.endorsement_count}
              pictureUrl={match.picture_url}
              nexusUrl={match.nexus_url}
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
}: Props) {
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
      {mods.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-text-primary mb-3">
            Managed Mods ({mods.length})
          </h3>
          <ManagedModsTable mods={mods} gameName={gameName} />
        </div>
      )}

      {recognized.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-text-primary mb-3">
            Recognized Mods ({recognized.length})
          </h3>
          <p className="text-xs text-text-muted mb-3">
            These mods were detected during scanning and matched to Nexus, but haven't been formally
            installed through the manager yet.
          </p>
          <RecognizedModsGrid
            mods={recognized}
            archives={archives}
            installedModIds={installedNexusIds}
            gameName={gameName}
            downloadJobs={downloadJobs}
          />
        </div>
      )}
    </div>
  );
}
