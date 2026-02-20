import {
  AlertTriangle,
  Check,
  Download,
  ExternalLink,
  Heart,
  Loader2,
  Search,
  User,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";

import { Badge, ConfidenceBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useCheckConflicts, useInstallMod } from "@/hooks/mutations";
import type {
  AvailableArchive,
  ConflictCheckResult,
  InstalledModOut,
  ModGroup,
} from "@/types/api";

type SortKey = "score" | "name" | "endorsements" | "author";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "score", label: "Match Score" },
  { value: "name", label: "Mod Name" },
  { value: "endorsements", label: "Endorsements" },
  { value: "author", label: "Author" },
];

const PLACEHOLDER_IMG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='320' height='180' fill='%231a1a2e'%3E%3Crect width='320' height='180'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%23555' font-size='14'%3ENo Image%3C/text%3E%3C/svg%3E";

interface Props {
  mods: ModGroup[];
  archives: AvailableArchive[];
  installedMods: InstalledModOut[];
  gameName: string;
}

export function NexusMatchedGrid({ mods, archives, installedMods, gameName }: Props) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [installingModIds, setInstallingModIds] = useState<Set<number>>(new Set());
  const [conflicts, setConflicts] = useState<ConflictCheckResult | null>(null);
  const [conflictModId, setConflictModId] = useState<number | null>(null);

  const installMod = useInstallMod();
  const checkConflicts = useCheckConflicts();

  // Pick the largest archive per nexus_mod_id (heuristic: bigger = more recent/complete)
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
      const match = m.nexus_match;
      return (
        m.display_name.toLowerCase().includes(q) ||
        (match?.mod_name.toLowerCase().includes(q) ?? false) ||
        (match?.author.toLowerCase().includes(q) ?? false)
      );
    });

    items.sort((a, b) => {
      const ma = a.nexus_match;
      const mb = b.nexus_match;
      if (!ma || !mb) return 0;
      switch (sortKey) {
        case "score":
          return mb.score - ma.score;
        case "name":
          return ma.mod_name.localeCompare(mb.mod_name);
        case "endorsements":
          return mb.endorsement_count - ma.endorsement_count;
        case "author":
          return ma.author.localeCompare(mb.author);
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

  // Close conflict dialog on Escape
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
      <p className="text-text-muted text-sm py-4">
        No Nexus-matched mods yet. Run a scan to discover and correlate mods.
      </p>
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
          const match = mod.nexus_match;
          if (!match) return null;

          const nexusModId = match.nexus_mod_id;
          const archive = nexusModId != null ? archiveByModId.get(nexusModId) : undefined;
          const isInstalled = nexusModId != null && installedModIds.has(nexusModId);
          const isInstalling = nexusModId != null && installingModIds.has(nexusModId);

          return (
            <div
              key={mod.id}
              className="rounded-xl border border-border bg-surface-1 overflow-hidden flex flex-col"
            >
              {/* Image */}
              <img
                src={match.picture_url || PLACEHOLDER_IMG}
                alt={match.mod_name}
                loading="lazy"
                className="w-full h-40 object-cover bg-surface-2"
                onError={(e) => {
                  (e.target as HTMLImageElement).src = PLACEHOLDER_IMG;
                }}
              />

              {/* Body */}
              <div className="p-4 flex flex-col flex-1 gap-2">
                {/* Title + Link */}
                <div className="flex items-start gap-2">
                  <h3 className="text-sm font-semibold text-text-primary leading-tight flex-1 line-clamp-2">
                    {match.mod_name}
                  </h3>
                  {match.nexus_url && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        openUrl(match.nexus_url).catch(() => {});
                      }}
                      className="text-accent hover:text-accent/80 shrink-0 mt-0.5"
                      title="Open on Nexus Mods"
                    >
                      <ExternalLink size={14} />
                    </button>
                  )}
                </div>

                {/* Summary */}
                {match.summary && (
                  <p className="text-xs text-text-muted line-clamp-2">
                    {match.summary}
                  </p>
                )}

                {/* Metadata row */}
                <div className="flex items-center gap-3 text-xs text-text-muted mt-auto pt-1">
                  {match.author && (
                    <span className="flex items-center gap-1 truncate">
                      <User size={12} />
                      {match.author}
                    </span>
                  )}
                  {match.version && (
                    <span className="truncate">v{match.version}</span>
                  )}
                  {match.endorsement_count > 0 && (
                    <span className="flex items-center gap-1">
                      <Heart size={12} />
                      {match.endorsement_count.toLocaleString()}
                    </span>
                  )}
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between pt-2 border-t border-border/50">
                  <div className="flex items-center gap-1.5">
                    <ConfidenceBadge score={match.score} />
                    <Badge variant="neutral">{match.method}</Badge>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs text-text-muted truncate max-w-[100px]" title={mod.display_name}>
                      {mod.display_name}
                    </span>
                    {isInstalled ? (
                      <Badge variant="success">
                        <Check size={10} /> Installed
                      </Badge>
                    ) : archive ? (
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
                    ) : null}
                  </div>
                </div>
              </div>
            </div>
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
