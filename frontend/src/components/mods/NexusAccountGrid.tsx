import {
  AlertTriangle,
  Check,
  Download,
  ExternalLink,
  Loader2,
  Search,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";

import { NexusModCard } from "@/components/mods/NexusModCard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useCheckConflicts, useInstallMod } from "@/hooks/mutations";
import type {
  AvailableArchive,
  ConflictCheckResult,
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
}

export function NexusAccountGrid({
  mods,
  archives,
  installedMods,
  gameName,
  emptyMessage,
}: Props) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("name");
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

  if (mods.length === 0) {
    return (
      <p className="text-text-muted text-sm py-4">{emptyMessage}</p>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
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

      {/* Card Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((mod) => {
          const nexusModId = mod.nexus_mod_id;
          const archive = archiveByModId.get(nexusModId);
          const isInstalled = installedModIds.has(nexusModId);
          const isInstalling = installingModIds.has(nexusModId);

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
                onClick={() => handleInstall(nexusModId, archive)}
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
          } else if (mod.nexus_url) {
            action = (
              <button
                onClick={() => openUrl(mod.nexus_url).catch(() => {})}
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
              modName={mod.mod_name}
              summary={mod.summary}
              author={mod.author}
              version={mod.version}
              endorsementCount={mod.endorsement_count}
              pictureUrl={mod.picture_url}
              nexusUrl={mod.nexus_url}
              action={action}
              footer={
                mod.version ? (
                  <span className="text-xs text-text-muted">v{mod.version}</span>
                ) : undefined
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
    </div>
  );
}
