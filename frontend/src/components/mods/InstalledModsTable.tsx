import {
  AlertTriangle,
  Check,
  Download,
  ExternalLink,
  Loader2,
  Power,
  PowerOff,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";

import { NexusModCard } from "@/components/mods/NexusModCard";
import { Badge, ConfidenceBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useCheckConflicts, useInstallMod, useToggleMod, useUninstallMod } from "@/hooks/mutations";
import { cn } from "@/lib/utils";
import type { AvailableArchive, ConflictCheckResult, InstalledModOut, ModGroup } from "@/types/api";

interface Props {
  mods: InstalledModOut[];
  gameName: string;
  recognizedMods?: ModGroup[];
  archives?: AvailableArchive[];
}

type SortKey = "name" | "version" | "files" | "disabled";

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
}: {
  mods: ModGroup[];
  archives: AvailableArchive[];
  installedModIds: Set<number>;
  gameName: string;
}) {
  const [installingModIds, setInstallingModIds] = useState<Set<number>>(new Set());
  const [conflicts, setConflicts] = useState<ConflictCheckResult | null>(null);
  const [conflictModId, setConflictModId] = useState<number | null>(null);

  const installMod = useInstallMod();
  const checkConflicts = useCheckConflicts();

  const archiveByModId = useMemo(() => {
    const map = new Map<number, AvailableArchive>();
    for (const a of archives) {
      if (a.nexus_mod_id == null) continue;
      const existing = map.get(a.nexus_mod_id);
      if (!existing || a.size > existing.size) {
        map.set(a.nexus_mod_id, a);
      }
    }
    return map;
  }, [archives]);

  const addInstalling = (id: number) =>
    setInstallingModIds((prev) => new Set(prev).add(id));
  const removeInstalling = (id: number) =>
    setInstallingModIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });

  useEffect(() => {
    if (!conflicts) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (conflictModId != null) removeInstalling(conflictModId);
        setConflicts(null);
        setConflictModId(null);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [conflicts, conflictModId]);

  const doInstall = async (fileName: string, skipConflicts: string[], nexusModId: number) => {
    try {
      await installMod.mutateAsync({
        gameName,
        data: { archive_filename: fileName, skip_conflicts: skipConflicts },
      });
    } finally {
      removeInstalling(nexusModId);
    }
  };

  const handleInstall = async (nexusModId: number, archive: AvailableArchive) => {
    addInstalling(nexusModId);
    try {
      const result = await checkConflicts.mutateAsync({
        gameName,
        archiveFilename: archive.filename,
      });

      if (result.conflicts.length > 0) {
        setConflicts(result);
        setConflictModId(nexusModId);
      } else {
        await doInstall(archive.filename, [], nexusModId);
      }
    } catch {
      removeInstalling(nexusModId);
    }
  };

  const handleInstallWithSkip = async () => {
    if (!conflicts || conflictModId == null) return;
    try {
      await doInstall(
        conflicts.archive_filename,
        conflicts.conflicts.map((c) => c.file_path),
        conflictModId,
      );
    } finally {
      setConflicts(null);
      setConflictModId(null);
    }
  };

  const handleInstallOverwrite = async () => {
    if (!conflicts || conflictModId == null) return;
    try {
      await doInstall(conflicts.archive_filename, [], conflictModId);
    } finally {
      setConflicts(null);
      setConflictModId(null);
    }
  };

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {mods.map((mod) => {
          const match = mod.nexus_match;
          if (!match) return null;

          const nexusModId = match.nexus_mod_id;
          const archive = nexusModId != null ? archiveByModId.get(nexusModId) : undefined;
          const isInstalled = nexusModId != null && installedModIds.has(nexusModId);
          const isInstalling = nexusModId != null && installingModIds.has(nexusModId);

          let action: React.ReactNode;
          if (isInstalled) {
            action = (
              <Badge variant="success">
                <Check size={10} /> Installed
              </Badge>
            );
          } else if (archive) {
            action = (
              <button
                onClick={() => handleInstall(nexusModId!, archive)}
                disabled={isInstalling || conflicts != null}
                className="inline-flex items-center gap-1 rounded-md bg-accent px-2 py-1 text-xs font-medium text-white hover:bg-accent/80 disabled:opacity-50"
                title={`Install from ${archive.filename}`}
              >
                {isInstalling ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Download size={12} />
                )}
                Install
              </button>
            );
          } else if (match.nexus_url) {
            action = (
              <button
                onClick={() => openUrl(match.nexus_url).catch(() => {})}
                className="inline-flex items-center gap-1 rounded-md bg-surface-2 px-2 py-1 text-xs font-medium text-text-secondary hover:bg-surface-2/80 border border-border"
              >
                <ExternalLink size={12} />
                Get on Nexus
              </button>
            );
          }

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
              action={action}
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

      {/* Conflict Dialog */}
      {conflicts && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg rounded-xl border border-border bg-surface-1 p-6">
            <div className="mb-4 flex items-center gap-2 text-warning">
              <AlertTriangle size={20} />
              <h3 className="text-lg font-semibold text-text-primary">
                File Conflicts Detected
              </h3>
            </div>
            <p className="mb-3 text-sm text-text-secondary">
              {conflicts.conflicts.length} file(s) conflict with installed mods:
            </p>
            <div className="mb-4 max-h-48 overflow-y-auto rounded border border-border bg-surface-0 p-3">
              {conflicts.conflicts.map((c) => (
                <div key={c.file_path} className="py-1 text-xs">
                  <span className="font-mono text-text-primary">{c.file_path}</span>
                  <span className="ml-2 text-text-muted">(owned by {c.owning_mod_name})</span>
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  if (conflictModId != null) removeInstalling(conflictModId);
                  setConflicts(null);
                  setConflictModId(null);
                }}
              >
                Cancel
              </Button>
              <Button variant="secondary" size="sm" onClick={handleInstallWithSkip}>
                Skip Conflicts
              </Button>
              <Button size="sm" onClick={handleInstallOverwrite}>
                Overwrite
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function InstalledModsTable({ mods, gameName, recognizedMods = [], archives = [] }: Props) {
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
          />
        </div>
      )}
    </div>
  );
}
