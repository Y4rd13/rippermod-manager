import { Check, Copy, Eye, ExternalLink, Heart, Info, Settings } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";

import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { FomodWizard } from "@/components/mods/FomodWizard";
import { ModCardAction } from "@/components/mods/ModCardAction";
import { ModQuickActions } from "@/components/mods/ModQuickActions";
import { NexusModCard } from "@/components/mods/NexusModCard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ContextMenu, type ContextMenuItem } from "@/components/ui/ContextMenu";
import { OverflowMenuButton } from "@/components/ui/OverflowMenuButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { SearchInput } from "@/components/ui/SearchInput";
import { SkeletonCardGrid } from "@/components/ui/SkeletonCard";
import { VirtualCardGrid } from "@/components/ui/VirtualCardGrid";
import { useAbstainMod, useEndorseMod, useTrackMod, useUntrackMod } from "@/hooks/mutations";
import { toast } from "@/stores/toast-store";
import { useContextMenu } from "@/hooks/use-context-menu";
import { useInstallFlow } from "@/hooks/use-install-flow";
import { useSessionState } from "@/hooks/use-session-state";
import { isoToEpoch, timeAgo } from "@/lib/format";
import type {
  AvailableArchive,
  DownloadJobOut,
  InstalledModOut,
  NexusDownload,
} from "@/types/api";


type SortKey = "name" | "endorsements" | "author" | "updated";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "updated", label: "Recently Updated" },
  { value: "name", label: "Mod Name" },
  { value: "endorsements", label: "Endorsements" },
  { value: "author", label: "Author" },
];

function getContextMenuItems(mod: NexusDownload): ContextMenuItem[] {
  return [
    { key: "details", label: "View Details", icon: Info },
    { key: "nexus", label: "Open on Nexus", icon: ExternalLink },
    { key: "copy-name", label: "Copy Name", icon: Copy },
    { key: "sep-actions", label: "", separator: true },
    {
      key: "endorse",
      label: mod.is_endorsed ? "Remove Endorsement" : "Endorse",
      icon: Heart,
    },
    {
      key: "track",
      label: mod.is_tracked ? "Untrack" : "Track",
      icon: Eye,
    },
  ];
}

interface Props {
  mods: NexusDownload[];
  archives: AvailableArchive[];
  installedMods: InstalledModOut[];
  gameName: string;
  emptyMessage: string;
  downloadJobs?: DownloadJobOut[];
  onModClick?: (nexusModId: number) => void;
  isLoading?: boolean;
  emptyIcon?: "heart" | "eye";
  emptyTitle?: string;
  dataUpdatedAt?: number;
}

export function NexusAccountGrid({
  mods,
  archives,
  installedMods,
  gameName,
  emptyMessage,
  downloadJobs = [],
  onModClick,
  isLoading = false,
  emptyIcon = "heart",
  emptyTitle = "No mods found",
  dataUpdatedAt,
}: Props) {
  const navigate = useNavigate();
  const [filter, setFilter] = useState("");
  const [isStale, setIsStale] = useState(false);

  useEffect(() => {
    if (dataUpdatedAt == null) return;
    const check = () => setIsStale(Date.now() - dataUpdatedAt > 30 * 60 * 1000);
    check();
    const timer = setInterval(check, 60_000);
    return () => clearInterval(timer);
  }, [dataUpdatedAt]);
  const [sortKey, setSortKey] = useSessionState<SortKey>(`account-sort-${gameName}`, "updated");
  const [chip, setChip] = useSessionState(`account-chip-${gameName}`, "all");

  const flow = useInstallFlow(gameName, archives, downloadJobs);
  const endorseMod = useEndorseMod();
  const abstainMod = useAbstainMod();
  const trackMod = useTrackMod();
  const untrackMod = useUntrackMod();
  const { menuState, openMenu, closeMenu } = useContextMenu<NexusDownload>();

  const installedModIds = useMemo(
    () => new Set(installedMods.filter((m) => m.nexus_mod_id != null).map((m) => m.nexus_mod_id!)),
    [installedMods],
  );

  const filtered = useMemo(() => {
    const q = filter.toLowerCase();
    let items = mods.filter((m) => {
      if (!q) return true;
      return m.mod_name.toLowerCase().includes(q) || m.author.toLowerCase().includes(q);
    });

    if (chip === "installed") items = items.filter((m) => installedModIds.has(m.nexus_mod_id));
    else if (chip === "not-installed") items = items.filter((m) => !installedModIds.has(m.nexus_mod_id));

    items.sort((a, b) => {
      switch (sortKey) {
        case "updated":
          return isoToEpoch(b.updated_at) - isoToEpoch(a.updated_at);
        case "name":
          return a.mod_name.localeCompare(b.mod_name);
        case "endorsements":
          return b.endorsement_count - a.endorsement_count;
        case "author":
          return a.author.localeCompare(b.author);
      }
    });

    return items;
  }, [mods, filter, sortKey, chip, installedModIds]);

  const chipCounts = useMemo(() => ({
    all: mods.length,
    installed: mods.filter((m) => installedModIds.has(m.nexus_mod_id)).length,
    "not-installed": mods.filter((m) => !installedModIds.has(m.nexus_mod_id)).length,
  }), [mods, installedModIds]);

  function handleContextMenuSelect(key: string) {
    const mod = menuState.data;
    if (!mod) return;
    if (key === "details") onModClick?.(mod.nexus_mod_id);
    else if (key === "nexus") window.open(mod.nexus_url, "_blank", "noopener,noreferrer");
    else if (key === "copy-name") void navigator.clipboard.writeText(mod.mod_name).then(
      () => toast.success("Copied to clipboard"),
      () => toast.error("Failed to copy"),
    );
    else if (key === "endorse") {
      if (mod.is_endorsed) abstainMod.mutate({ gameName, modId: mod.nexus_mod_id });
      else endorseMod.mutate({ gameName, modId: mod.nexus_mod_id });
    } else if (key === "track") {
      if (mod.is_tracked) untrackMod.mutate({ gameName, modId: mod.nexus_mod_id });
      else trackMod.mutate({ gameName, modId: mod.nexus_mod_id });
    }
  }

  if (isLoading) {
    return <SkeletonCardGrid />;
  }

  const EmptyIcon = emptyIcon === "eye" ? Eye : Heart;

  if (mods.length === 0) {
    return (
      <EmptyState
        icon={EmptyIcon}
        title={emptyTitle}
        description={emptyMessage}
        actions={
          <Button size="sm" variant="secondary" onClick={() => navigate("/settings")}>
            <Settings size={14} /> Nexus Settings
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <SearchInput value={filter} onChange={setFilter} placeholder="Filter by name or author..." />
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
        {isStale && dataUpdatedAt != null && (
          <span className="text-xs text-warning" title="Data may be outdated — sync your Nexus account to update">
            Updated {timeAgo(Math.floor(dataUpdatedAt / 1000))}
          </span>
        )}
      </div>

      <FilterChips
        chips={[
          { key: "all", label: "All", count: chipCounts.all },
          { key: "installed", label: "Installed", count: chipCounts.installed },
          { key: "not-installed", label: "Not Installed", count: chipCounts["not-installed"] },
        ]}
        active={chip}
        onChange={setChip}
      />

      <VirtualCardGrid
        items={filtered}
        renderItem={(mod) => {
          const nexusModId = mod.nexus_mod_id;
          const archive = flow.archiveByModId.get(nexusModId);

          return (
            <NexusModCard
              modName={mod.mod_name}
              summary={mod.summary}
              author={mod.author}
              version={mod.version}
              endorsementCount={mod.endorsement_count}
              pictureUrl={mod.picture_url}
              onClick={() => onModClick?.(nexusModId)}
              onContextMenu={(e) => openMenu(e, mod)}
              badge={
                (installedModIds.has(nexusModId) || mod.is_tracked || mod.is_endorsed) ? (
                  <div className="flex items-center gap-1">
                    {installedModIds.has(nexusModId) && (
                      <Badge variant="success">
                        <Check size={10} className="mr-0.5" />
                        Installed
                      </Badge>
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
                ) : undefined
              }
              footer={
                <div className="flex items-center gap-2">
                  {mod.updated_at && (
                    <span className="text-xs text-text-muted">{timeAgo(isoToEpoch(mod.updated_at))}</span>
                  )}
                  <ModQuickActions
                    isEndorsed={mod.is_endorsed}
                    isTracked={mod.is_tracked}
                    modId={nexusModId}
                    gameName={gameName}
                  />
                </div>
              }
              action={
                <ModCardAction
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
              overflowMenu={
                <OverflowMenuButton
                  items={getContextMenuItems(mod)}
                  onSelect={(key) => {
                    if (key === "details") onModClick?.(nexusModId);
                    else if (key === "nexus") window.open(mod.nexus_url, "_blank", "noopener,noreferrer");
                    else if (key === "copy-name") void navigator.clipboard.writeText(mod.mod_name).then(
                      () => toast.success("Copied to clipboard"),
                      () => toast.error("Failed to copy"),
                    );
                    else if (key === "endorse") {
                      if (mod.is_endorsed) abstainMod.mutate({ gameName, modId: nexusModId });
                      else endorseMod.mutate({ gameName, modId: nexusModId });
                    } else if (key === "track") {
                      if (mod.is_tracked) untrackMod.mutate({ gameName, modId: nexusModId });
                      else trackMod.mutate({ gameName, modId: nexusModId });
                    }
                  }}
                />
              }
            />
          );
        }}
      />

      {flow.fomodArchive && (
        <FomodWizard gameName={gameName} archiveFilename={flow.fomodArchive} onDismiss={flow.dismissFomod} onInstallComplete={flow.dismissFomod} />
      )}

      {flow.conflicts && (
        <ConflictDialog
          conflicts={flow.conflicts}
          onCancel={flow.dismissConflicts}
          onSkip={flow.handleInstallWithSkip}
          onOverwrite={flow.handleInstallOverwrite}
        />
      )}

      {menuState.visible && menuState.data && (
        <ContextMenu
          items={getContextMenuItems(menuState.data)}
          position={menuState.position}
          onSelect={handleContextMenuSelect}
          onClose={closeMenu}
        />
      )}
    </div>
  );
}
