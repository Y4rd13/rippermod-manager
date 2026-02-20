import {
  Check,
  Download,
  ExternalLink,
  Loader2,
  Search,
} from "lucide-react";
import { useMemo, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";

import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { NexusModCard } from "@/components/mods/NexusModCard";
import { Badge, ConfidenceBadge } from "@/components/ui/Badge";
import { useInstallFlow } from "@/hooks/use-install-flow";
import type {
  AvailableArchive,
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

interface Props {
  mods: ModGroup[];
  archives: AvailableArchive[];
  installedMods: InstalledModOut[];
  gameName: string;
}

export function NexusMatchedGrid({ mods, archives, installedMods, gameName }: Props) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("score");

  const {
    archiveByModId,
    installingModIds,
    conflicts,
    handleInstall,
    handleInstallWithSkip,
    handleInstallOverwrite,
    dismissConflicts,
  } = useInstallFlow(gameName, archives);

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
                  <span className="text-xs text-text-muted truncate max-w-[100px]" title={mod.display_name}>
                    {mod.display_name}
                  </span>
                </div>
              }
            />
          );
        })}
      </div>

      {conflicts && (
        <ConflictDialog
          conflicts={conflicts}
          onCancel={dismissConflicts}
          onSkip={handleInstallWithSkip}
          onOverwrite={handleInstallOverwrite}
        />
      )}
    </div>
  );
}
