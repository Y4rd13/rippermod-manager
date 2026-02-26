import { CheckCircle, FileText, Link2, Pencil, X, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "@/stores/toast-store";

import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { FomodWizard } from "@/components/mods/FomodWizard";
import { PreInstallPreview } from "@/components/mods/PreInstallPreview";
import { CorrelationActions } from "@/components/mods/CorrelationActions";
import { ReassignDialog } from "@/components/mods/ReassignDialog";
import { ModCardAction } from "@/components/mods/ModCardAction";
import { NexusModCard } from "@/components/mods/NexusModCard";
import { Badge, ConfidenceBadge } from "@/components/ui/Badge";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ContextMenu, type ContextMenuItem } from "@/components/ui/ContextMenu";
import { OverflowMenuButton } from "@/components/ui/OverflowMenuButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { FileTreeView } from "@/components/ui/FileTreeView";
import { buildFileTree } from "@/lib/file-tree";
import { FilterChips } from "@/components/ui/FilterChips";
import { SearchInput } from "@/components/ui/SearchInput";
import { SkeletonCardGrid } from "@/components/ui/SkeletonCard";
import { VirtualCardGrid } from "@/components/ui/VirtualCardGrid";
import { useContextMenu } from "@/hooks/use-context-menu";
import { useConfirmCorrelation, useRejectCorrelation } from "@/hooks/mutations";
import { useInstallFlow } from "@/hooks/use-install-flow";
import { useSessionState } from "@/hooks/use-session-state";
import { isoToEpoch, timeAgo } from "@/lib/format";
import type {
  AvailableArchive,
  DownloadJobOut,
  InstalledModOut,
  ModGroup,
} from "@/types/api";

function FilesModal({ group, onClose }: { group: ModGroup; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="files-dialog-title"
        className="w-full max-w-2xl rounded-xl border border-border bg-surface-1 p-6 animate-modal-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 id="files-dialog-title" className="text-sm font-semibold text-text-primary truncate pr-4">
            {group.nexus_match?.mod_name ?? group.display_name}
          </h3>
          <button
            onClick={onClose}
            className="shrink-0 rounded-md p-1 text-text-muted hover:bg-surface-3 hover:text-text-primary"
          >
            <X size={16} />
          </button>
        </div>
        <p className="mb-3 text-xs text-text-muted">
          {group.files.length} file{group.files.length !== 1 ? "s" : ""}
        </p>
        <div className="max-h-80 overflow-y-auto rounded border border-border bg-surface-0 p-3">
          <FileTreeView tree={buildFileTree(group.files)} />
        </div>
      </div>
    </div>
  );
}

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
  { key: "high", label: "High (90%+)" },
  { key: "medium", label: "Medium (75-89%)" },
  { key: "low", label: "Low (<75%)" },
];

const METHOD_LABELS: Record<string, string> = {
  exact: "Exact",
  substring: "Substring",
  fuzzy: "Fuzzy",
  filename_id: "Filename ID",
  installed: "Installed",
  file_list: "File List",
  endorsed_name: "Endorsed",
  fomod: "FOMOD",
  ai_search: "AI Search",
  web_search: "Web Search",
  manual: "Manual",
};

interface Props {
  mods: ModGroup[];
  archives: AvailableArchive[];
  installedMods: InstalledModOut[];
  gameName: string;
  downloadJobs?: DownloadJobOut[];
  isLoading?: boolean;
  onModClick?: (nexusModId: number) => void;
  onFileSelect?: (nexusModId: number) => void;
}

export function NexusMatchedGrid({
  mods,
  archives,
  installedMods,
  gameName,
  downloadJobs = [],
  isLoading,
  onModClick,
  onFileSelect,
}: Props) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useSessionState<SortKey>(`matched-sort-${gameName}`, "updated");
  const [chip, setChip] = useSessionState(`matched-chip-${gameName}`, "all");
  const [methodChip, setMethodChip] = useSessionState(`matched-method-${gameName}`, "all");
  const [installChip, setInstallChip] = useSessionState(`matched-install-${gameName}`, "all");

  const flow = useInstallFlow(gameName, archives, downloadJobs, onFileSelect);
  const { menuState, openMenu, closeMenu } = useContextMenu<ModGroup>();

  const installedModIds = useMemo(
    () => new Set(installedMods.filter((m) => m.nexus_mod_id != null).map((m) => m.nexus_mod_id!)),
    [installedMods],
  );

  const methodChips = useMemo(() => {
    const counts = new Map<string, number>();
    for (const m of mods) {
      const method = m.nexus_match?.method;
      if (method) counts.set(method, (counts.get(method) ?? 0) + 1);
    }
    const chips: { key: string; label: string; count?: number }[] = [{ key: "all", label: "All" }];
    for (const [key, count] of [...counts.entries()].sort((a, b) => b[1] - a[1])) {
      chips.push({ key, label: METHOD_LABELS[key] ?? key, count });
    }
    return chips;
  }, [mods]);

  useEffect(() => {
    if (methodChip !== "all" && !methodChips.some((c) => c.key === methodChip)) {
      setMethodChip("all");
    }
  }, [methodChips, methodChip, setMethodChip]);

  const installChips = useMemo(() => {
    let installedCount = 0;
    let notInstalledCount = 0;
    for (const m of mods) {
      const nexusId = m.nexus_match?.nexus_mod_id;
      if (nexusId != null && installedModIds.has(nexusId)) installedCount++;
      else notInstalledCount++;
    }
    return [
      { key: "all", label: "All" },
      { key: "installed", label: "Installed", count: installedCount },
      { key: "not-installed", label: "Not Installed", count: notInstalledCount },
    ];
  }, [mods, installedModIds]);

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

    if (methodChip !== "all")
      items = items.filter((m) => m.nexus_match?.method === methodChip);

    if (installChip === "installed")
      items = items.filter((m) => {
        const nexusId = m.nexus_match?.nexus_mod_id;
        return nexusId != null && installedModIds.has(nexusId);
      });
    else if (installChip === "not-installed")
      items = items.filter((m) => {
        const nexusId = m.nexus_match?.nexus_mod_id;
        return nexusId == null || !installedModIds.has(nexusId);
      });

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
  }, [mods, filter, sortKey, chip, methodChip, installChip, installedModIds]);

  const confirmCorrelation = useConfirmCorrelation();
  const rejectCorrelation = useRejectCorrelation();
  const [reassignGroupId, setReassignGroupId] = useState<number | null>(null);
  const [rejectModId, setRejectModId] = useState<number | null>(null);
  const [filesModalGroupId, setFilesModalGroupId] = useState<number | null>(null);

  const contextMenuItems: ContextMenuItem[] = [
    { key: "view", label: "View Details" },
    { key: "open-nexus", label: "Open on Nexus" },
    { key: "copy-name", label: "Copy Name" },
    { key: "sep-corr", label: "", separator: true },
    { key: "accept-match", label: "Accept Match", icon: CheckCircle },
    { key: "reject-match", label: "Reject Match", icon: XCircle },
    { key: "correct-match", label: "Correct Match", icon: Pencil },
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
      void navigator.clipboard.writeText(match.mod_name).then(
        () => toast.success("Copied to clipboard"),
        () => toast.error("Failed to copy"),
      );
    } else if (key === "accept-match") {
      confirmCorrelation.mutate({ gameName, modGroupId: mod.id });
    } else if (key === "reject-match") {
      setRejectModId(mod.id);
    } else if (key === "correct-match") {
      setReassignGroupId(mod.id);
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
      </div>

      <FilterChips chips={CONFIDENCE_CHIPS} active={chip} onChange={setChip} />
      <FilterChips chips={methodChips} active={methodChip} onChange={setMethodChip} />
      <FilterChips chips={installChips} active={installChip} onChange={setInstallChip} />

      <VirtualCardGrid
        items={filtered}
        renderItem={(mod) => {
          const match = mod.nexus_match;
          if (!match) return null;

          const nexusModId = match.nexus_mod_id;
          const archive = nexusModId != null ? flow.archiveByModId.get(nexusModId) : undefined;
          const dl = nexusModId != null ? flow.completedDownloadByModId.get(nexusModId) : undefined;

          return (
            <div className="flex flex-col">
              <div className="flex-1 grid">
                <NexusModCard
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
                      completedDownload={dl}
                      archive={archive}
                      nexusUrl={match.nexus_url}
                      hasConflicts={flow.conflicts != null}
                      isDownloading={flow.downloadingModId === nexusModId}
                      onInstall={() => nexusModId != null && archive && flow.handleInstall(nexusModId, archive)}
                      onInstallByFilename={() => {
                        if (nexusModId != null && dl) flow.handleInstallByFilename(nexusModId, dl.file_name);
                      }}
                      onDownload={() => nexusModId != null && flow.handleDownload(nexusModId)}
                      onCancelDownload={() => {
                        const activeDl = nexusModId != null ? flow.activeDownloadByModId.get(nexusModId) : undefined;
                        if (activeDl) flow.handleCancelDownload(activeDl.id);
                      }}
                      onInstallWithPreview={
                        nexusModId != null && dl
                          ? () => flow.handleInstallWithPreviewByFilename(nexusModId, dl.file_name)
                          : nexusModId != null && archive
                            ? () => flow.handleInstallWithPreview(nexusModId, archive)
                            : undefined
                      }
                    />
                  }
                  overflowMenu={
                    <OverflowMenuButton
                      items={contextMenuItems}
                      onSelect={(key) => {
                        if (key === "view" && nexusModId != null) onModClick?.(nexusModId);
                        else if (key === "open-nexus" && match.nexus_url) window.open(match.nexus_url, "_blank", "noopener,noreferrer");
                        else if (key === "copy-name") void navigator.clipboard.writeText(match.mod_name).then(
                          () => toast.success("Copied to clipboard"),
                          () => toast.error("Failed to copy"),
                        );
                        else if (key === "accept-match") confirmCorrelation.mutate({ gameName, modGroupId: mod.id });
                        else if (key === "reject-match") setRejectModId(mod.id);
                        else if (key === "correct-match") setReassignGroupId(mod.id);
                      }}
                    />
                  }
                  footer={
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <ConfidenceBadge score={match.score} />
                      <Badge variant="neutral">{match.method}</Badge>
                      <CorrelationActions
                        gameName={gameName}
                        modGroupId={mod.id}
                        confirmed={match.confirmed}
                      />
                      {match.updated_at && (
                        <span className="text-xs text-text-muted">{timeAgo(isoToEpoch(match.updated_at))}</span>
                      )}
                      {mod.earliest_file_mtime != null && (
                        <span className="text-xs text-text-muted" title="File date on disk">
                          DL: {timeAgo(mod.earliest_file_mtime)}
                        </span>
                      )}
                      {mod.files.length > 0 && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setFilesModalGroupId(mod.id);
                          }}
                          className="ml-auto flex items-center gap-1 text-xs text-accent hover:underline"
                        >
                          <FileText size={12} />
                          {mod.files.length} file{mod.files.length !== 1 ? "s" : ""}
                        </button>
                      )}
                    </div>
                  }
                />
              </div>
            </div>
          );
        }}
      />

      {flow.previewArchive && (
        <PreInstallPreview
          gameName={gameName}
          archiveFilename={flow.previewArchive.filename}
          onConfirm={(renames) => flow.confirmPreviewInstall(renames)}
          onCancel={flow.dismissPreview}
        />
      )}

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

      {menuState.visible && (
        <ContextMenu
          items={contextMenuItems}
          position={menuState.position}
          onSelect={handleContextMenuSelect}
          onClose={closeMenu}
        />
      )}

      {rejectModId != null && (
        <ConfirmDialog
          title="Reject Match?"
          message="Remove this Nexus match? The mod will appear as unmatched."
          confirmLabel="Reject"
          variant="danger"
          icon={XCircle}
          loading={rejectCorrelation.isPending}
          onConfirm={async () => {
            await rejectCorrelation.mutateAsync({ gameName, modGroupId: rejectModId });
            setRejectModId(null);
          }}
          onCancel={() => setRejectModId(null)}
        />
      )}

      {reassignGroupId != null && (
        <ReassignDialog
          gameName={gameName}
          modGroupId={reassignGroupId}
          onClose={() => setReassignGroupId(null)}
        />
      )}

      {filesModalGroupId != null && (() => {
        const group = mods.find((m) => m.id === filesModalGroupId);
        return group ? <FilesModal group={group} onClose={() => setFilesModalGroupId(null)} /> : null;
      })()}
    </div>
  );
}
