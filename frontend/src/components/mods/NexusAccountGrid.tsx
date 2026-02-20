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
import { Badge } from "@/components/ui/Badge";
import { useInstallFlow } from "@/hooks/use-install-flow";
import type {
  AvailableArchive,
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
