import { Link2, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { ModCardAction } from "@/components/mods/ModCardAction";
import { NexusModCard } from "@/components/mods/NexusModCard";
import { Badge, ConfidenceBadge } from "@/components/ui/Badge";
import { ContextMenu, type ContextMenuItem } from "@/components/ui/ContextMenu";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { SkeletonCardGrid } from "@/components/ui/SkeletonCard";
import { useContextMenu } from "@/hooks/use-context-menu";
import { useInstallFlow } from "@/hooks/use-install-flow";
import { isoToEpoch, timeAgo } from "@/lib/format";
import type {
  AvailableArchive,
  DownloadJobOut,
  InstalledModOut,
  ModGroup,
} from "@/types/api";

type SortKey = "score" | "name" | "endorsements" | "author" | "updated";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "score", label: "Match Score" },
  { value: "updated", label: "Recently Updated" },
  { value: "name", label: "Mod Name" },
  { value: "endorsements", label: "Endorsements" },
  { value: "author", label: "Author" },
];

const CONFIDENCE_CHIPS = [
  { key: "all", label: "All" },
  { key: "high", label: "High" },
  { key: "medium", label: "Medium" },
  { key: "low", label: "Low" },
];

interface Props {
  mods: ModGroup[];
  archives: AvailableArchive[];
  installedMods: InstalledModOut[];
  gameName: string;
  downloadJobs?: DownloadJobOut[];
  isLoading?: boolean;
  onModClick?: (nexusModId: number) => void;
}

export function NexusMatchedGrid({
  mods,
  archives,
  installedMods,
  gameName,
  downloadJobs = [],
  isLoading,
  onModClick,
}: Props) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [chip, setChip] = useState("all");

  const flow = useInstallFlow(gameName, archives, downloadJobs);
  const { menuState, openMenu, closeMenu } = useContextMenu<ModGroup>();

  const installedModIds = useMemo(
    () => new Set(installedMods.filter((m) => m.nexus_mod_id != null).map((m) => m.nexus_mod_id!)),
    [installedMods],
  );

  const filtered = useMemo(() => {
    const q = filter.toLowerCase();
    let items = mods.filter((m) => {
      if (!q) return true;
      const match = m.nexus_match;
      return (
        m.display_name.toLowerCase().includes(q) ||
        (match?.mod_name.toLowerCase().includes(q) ?? false) ||
        (match?.author.toLowerCase().includes(q) ?? false)
      );
    });

    if (chip === "high") items = items.filter((m) => (m.nexus_match?.score ?? 0) >= 0.9);
    else if (chip === "medium")
      items = items.filter((m) => {
        const s = m.nexus_match?.score ?? 0;
        return s >= 0.75 && s < 0.9;
      });
    else if (chip === "low") items = items.filter((m) => (m.nexus_match?.score ?? 0) < 0.75);

    items.sort((a, b) => {
      const ma = a.nexus_match;
      const mb = b.nexus_match;
      if (!ma || !mb) return 0;
      switch (sortKey) {
        case "score":
          return mb.score - ma.score;
        case "updated":
          return isoToEpoch(mb.updated_at) - isoToEpoch(ma.updated_at);
        case "name":
          return ma.mod_name.localeCompare(mb.mod_name);
        case "endorsements":
          return mb.endorsement_count - ma.endorsement_count;
        case "author":
          return ma.author.localeCompare(mb.author);
      }
    });

    return items;
  }, [mods, filter, sortKey, chip]);

  const contextMenuItems: ContextMenuItem[] = [
    { key: "view", label: "View Details" },
    { key: "open-nexus", label: "Open on Nexus" },
    { key: "copy-name", label: "Copy Name" },
  ];

  function handleContextMenuSelect(key: string) {
    const mod = menuState.data;
    if (!mod) return;
    const match = mod.nexus_match;
    if (key === "view" && match?.nexus_mod_id != null) {
      onModClick?.(match.nexus_mod_id);
    } else if (key === "open-nexus" && match?.nexus_url) {
      window.open(match.nexus_url, "_blank", "noopener,noreferrer");
    } else if (key === "copy-name" && match?.mod_name) {
      navigator.clipboard.writeText(match.mod_name);
    }
  }

  if (isLoading) {
    return <SkeletonCardGrid count={6} />;
  }

  if (mods.length === 0) {
    return (
      <EmptyState
        icon={Link2}
        title="No Nexus Matches"
        description="Run a scan to discover and correlate your local mods with Nexus."
      />
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

      <FilterChips chips={CONFIDENCE_CHIPS} active={chip} onChange={setChip} />

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((mod) => {
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
              onClick={nexusModId != null ? () => onModClick?.(nexusModId) : undefined}
              onContextMenu={(e) => openMenu(e, mod)}
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
                <div className="flex items-center gap-1.5 flex-wrap">
                  <ConfidenceBadge score={match.score} />
                  <Badge variant="neutral">{match.method}</Badge>
                  <span className="text-xs text-text-muted truncate max-w-[120px]" title={mod.display_name}>
                    {mod.display_name}
                  </span>
                  {match.updated_at && (
                    <span className="text-xs text-text-muted">{timeAgo(isoToEpoch(match.updated_at))}</span>
                  )}
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

      {menuState.visible && (
        <ContextMenu
          items={contextMenuItems}
          position={menuState.position}
          onSelect={handleContextMenuSelect}
          onClose={closeMenu}
        />
      )}
    </div>
  );
}
