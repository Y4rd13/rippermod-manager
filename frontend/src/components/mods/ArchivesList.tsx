import { AlertTriangle, Archive, Check, ChevronDown, Copy, Download, ExternalLink, FolderOpen, FolderTree, Link, PackageMinus, Settings2, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { openPath } from "@tauri-apps/plugin-opener";

import { ArchiveTreeModal } from "@/components/mods/ArchiveTreeModal";
import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { FomodWizard } from "@/components/mods/FomodWizard";
import { PreInstallPreview } from "@/components/mods/PreInstallPreview";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { BulkActionBar } from "@/components/ui/BulkActionBar";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ContextMenu, type ContextMenuItem } from "@/components/ui/ContextMenu";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { SearchInput } from "@/components/ui/SearchInput";
import { SkeletonTable } from "@/components/ui/SkeletonTable";
import { SortSelect } from "@/components/ui/SortSelect";
import { VirtualTable } from "@/components/ui/VirtualTable";
import {
  useCheckConflicts,
  useCleanupOrphans,
  useDeleteArchive,
  useInstallMod,
  useLinkArchiveToNexus,
  useUninstallMod,
} from "@/hooks/mutations";
import { toast } from "@/stores/toast-store";
import { useBulkSelect } from "@/hooks/use-bulk-select";
import { useSessionState } from "@/hooks/use-session-state";
import { useContextMenu } from "@/hooks/use-context-menu";
import { formatBytes, isoToEpoch, timeAgo } from "@/lib/format";
import type {
  AvailableArchive,
  ConflictCheckResult,
} from "@/types/api";

interface Props {
  archives: AvailableArchive[];
  gameName: string;
  gameDomain: string;
  installPath: string;
  isLoading?: boolean;
}

type ArchiveSortKey = "name" | "size" | "version";

type LinkChip = "all" | "linked" | "unlinked" | "installed" | "orphan";

const ARCHIVE_SORT_OPTIONS: { value: ArchiveSortKey; label: string }[] = [
  { value: "name", label: "Name" },
  { value: "size", label: "Size" },
  { value: "version", label: "Version" },
];

function buildContextItems(archive: AvailableArchive): ContextMenuItem[] {
  const items: ContextMenuItem[] = [];
  if (archive.is_empty && archive.nexus_mod_id) {
    items.push({ key: "nexus", label: "View on Nexus", icon: ExternalLink });
  } else if (archive.is_installed && archive.installed_mod_id) {
    items.push({ key: "uninstall", label: "Uninstall", icon: PackageMinus, variant: "danger" });
  } else {
    items.push({ key: "install", label: "Install", icon: Download });
  }
  if (archive.nexus_mod_id && !archive.is_empty) {
    items.push({ key: "nexus", label: "View on Nexus", icon: ExternalLink });
  }
  items.push({ key: "copy", label: "Copy Filename", icon: Copy });
  items.push({ key: "delete", label: "Delete Archive", icon: Trash2, variant: "danger" });
  return items;
}

export function ArchivesList({ archives, gameName, gameDomain, installPath, isLoading }: Props) {
  const installMod = useInstallMod();
  const uninstallMod = useUninstallMod();
  const checkConflicts = useCheckConflicts();
  const deleteArchive = useDeleteArchive();
  const cleanupOrphans = useCleanupOrphans();
  const linkArchive = useLinkArchiveToNexus();
  const [conflicts, setConflicts] = useState<ConflictCheckResult | null>(null);
  const [confirmUninstall, setConfirmUninstall] = useState<{ filename: string; modId: number } | null>(null);
  const [fomodArchive, setFomodArchive] = useState<string | null>(null);
  const [selectedArchive, setSelectedArchive] = useState<string | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [confirmDeleteFile, setConfirmDeleteFile] = useState<string | null>(null);
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false);
  const [treeFilename, setTreeFilename] = useState<string | null>(null);
  const [previewFilename, setPreviewFilename] = useState<string | null>(null);
  const [pendingRenames, setPendingRenames] = useState<Record<string, string>>({});
  const [splitMenuPos, setSplitMenuPos] = useState<{ top: number; left: number; filename: string } | null>(null);
  const [linkPopover, setLinkPopover] = useState<{ top: number; left: number; filename: string } | null>(null);
  const [linkInput, setLinkInput] = useState("");
  const splitMenuRef = useRef<HTMLDivElement>(null);
  const linkPopoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!splitMenuPos) return;
    const handleClick = (e: MouseEvent) => {
      if (splitMenuRef.current?.contains(e.target as Node)) return;
      setSplitMenuPos(null);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [splitMenuPos]);

  useEffect(() => {
    if (!linkPopover) return;
    const handleClick = (e: MouseEvent) => {
      if (linkPopoverRef.current?.contains(e.target as Node)) return;
      setLinkPopover(null);
      setLinkInput("");
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [linkPopover]);

  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useSessionState<ArchiveSortKey>(`archives-sort-${gameName}`, "name");
  const [sortDir, setSortDir] = useSessionState<"asc" | "desc">(`archives-dir-${gameName}`, "asc");
  const [linkChip, setLinkChip] = useSessionState<LinkChip>(`archives-chip-${gameName}`, "all");

  const { menuState, openMenu, closeMenu } = useContextMenu<AvailableArchive>();

  const filtered = useMemo(() => {
    const q = filter.toLowerCase();
    const items = archives.filter((a) => {
      if (linkChip === "linked" && a.nexus_mod_id == null) return false;
      if (linkChip === "unlinked" && a.nexus_mod_id != null) return false;
      if (linkChip === "installed" && !a.is_installed) return false;
      if (linkChip === "orphan" && a.is_installed) return false;
      if (!q) return true;
      return (
        a.filename.toLowerCase().includes(q) ||
        a.parsed_name.toLowerCase().includes(q)
      );
    });

    items.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "name":
          cmp = a.parsed_name.localeCompare(b.parsed_name);
          break;
        case "size":
          cmp = a.size - b.size;
          break;
        case "version":
          cmp = (a.parsed_version ?? "").localeCompare(b.parsed_version ?? "", undefined, { numeric: true });
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });

    return items;
  }, [archives, filter, sortKey, sortDir, linkChip]);

  const bulk = useBulkSelect(filtered.map((a) => a.filename));

  const linkedCount = useMemo(
    () => archives.filter((a) => a.nexus_mod_id != null).length,
    [archives],
  );

  const unlinkedCount = useMemo(
    () => archives.filter((a) => a.nexus_mod_id == null).length,
    [archives],
  );

  const installedCount = useMemo(
    () => archives.filter((a) => a.is_installed).length,
    [archives],
  );

  const orphanCount = useMemo(
    () => archives.filter((a) => !a.is_installed).length,
    [archives],
  );

  const filterChips = [
    { key: "all", label: "All", count: archives.length },
    { key: "linked", label: "Linked", count: linkedCount },
    { key: "unlinked", label: "Unlinked", count: unlinkedCount },
    { key: "installed", label: "Installed", count: installedCount },
    { key: "orphan", label: "Orphan", count: orphanCount },
  ];

  const installQueueRef = useRef<string[]>([]);
  const [queueProgress, setQueueProgress] = useState<{ current: number; total: number } | null>(null);

  const processNextInQueue = () => {
    if (installQueueRef.current.length === 0) {
      setQueueProgress(null);
      return;
    }
    setQueueProgress((prev) => prev ? { ...prev, current: prev.current + 1 } : null);
    const next = installQueueRef.current.shift()!;
    handleCheckConflicts(next).catch(() => processNextInQueue());
  };

  const handleCheckConflicts = async (filename: string) => {
    setSelectedArchive(filename);
    const result = await checkConflicts.mutateAsync({ gameName, archiveFilename: filename });
    if (result.is_fomod) {
      setFomodArchive(filename);
      setSelectedArchive(null);
      processNextInQueue();
      return;
    }
    if (result.conflicts.length > 0) {
      setConflicts(result);
    } else {
      installMod.mutate({ gameName, data: { archive_filename: filename, skip_conflicts: [] } });
      processNextInQueue();
    }
  };

  const handleInstallWithSkip = () => {
    if (!conflicts) return;
    installMod.mutate({
      gameName,
      data: {
        archive_filename: conflicts.archive_filename,
        skip_conflicts: conflicts.conflicts.map((c) => c.file_path),
        ...(Object.keys(pendingRenames).length > 0 ? { file_renames: pendingRenames } : {}),
      },
    });
    setConflicts(null);
    setSelectedArchive(null);
    setPendingRenames({});
    processNextInQueue();
  };

  const handleInstallOverwrite = () => {
    if (!conflicts) return;
    installMod.mutate({
      gameName,
      data: {
        archive_filename: conflicts.archive_filename,
        skip_conflicts: [],
        ...(Object.keys(pendingRenames).length > 0 ? { file_renames: pendingRenames } : {}),
      },
    });
    setConflicts(null);
    setSelectedArchive(null);
    setPendingRenames({});
    processNextInQueue();
  };

  const handleBulkInstall = () => {
    const items = [...bulk.selectedIds];
    installQueueRef.current = items;
    setQueueProgress({ current: 0, total: items.length });
    bulk.deselectAll();
    processNextInQueue();
  };

  const handleInstallWithRenames = async (fileRenames: Record<string, string>) => {
    if (!previewFilename) return;
    const filename = previewFilename;
    setPreviewFilename(null);
    setSelectedArchive(filename);
    try {
      const result = await checkConflicts.mutateAsync({ gameName, archiveFilename: filename });
      if (result.is_fomod) {
        setFomodArchive(filename);
        setSelectedArchive(null);
        return;
      }
      if (result.conflicts.length > 0) {
        setConflicts(result);
        setPendingRenames(fileRenames);
      } else {
        installMod.mutate({
          gameName,
          data: {
            archive_filename: filename,
            skip_conflicts: [],
            ...(Object.keys(fileRenames).length > 0 ? { file_renames: fileRenames } : {}),
          },
        });
        setSelectedArchive(null);
      }
    } catch {
      setSelectedArchive(null);
    }
  };

  const handleContextMenuSelect = (key: string) => {
    const archive = menuState.data;
    if (!archive) return;
    if (key === "uninstall" && archive.installed_mod_id) {
      setConfirmUninstall({ filename: archive.filename, modId: archive.installed_mod_id });
    } else if (key === "install") {
      handleCheckConflicts(archive.filename);
    } else if (key === "copy") {
      void navigator.clipboard.writeText(archive.filename).then(
        () => toast.success("Copied to clipboard"),
        () => toast.error("Failed to copy"),
      );
    } else if (key === "nexus" && archive.nexus_mod_id) {
      window.open(`https://www.nexusmods.com/${gameDomain}/mods/${archive.nexus_mod_id}?tab=files`, "_blank", "noopener,noreferrer");
    } else if (key === "delete") {
      setConfirmDeleteFile(archive.filename);
    }
  };

  useEffect(() => {
    if (!conflicts) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setConflicts(null);
        setSelectedArchive(null);
        processNextInQueue();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [conflicts]);

  if (isLoading) {
    return <SkeletonTable columns={6} rows={5} />;
  }

  if (archives.length === 0) {
    return (
      <EmptyState
        icon={Archive}
        title="No Archives Found"
        description="Place mod archives (.zip, .7z, .rar) in the 'downloaded_mods' folder inside the game directory."
      />
    );
  }

  return (
    <>
      <div className="space-y-4">
        <FilterChips
          chips={filterChips}
          active={linkChip}
          onChange={(key) => setLinkChip(key as LinkChip)}
        />

        <div className="flex items-center gap-3">
          <SearchInput value={filter} onChange={setFilter} placeholder="Filter by filename..." />
          <SortSelect
            value={sortKey}
            onChange={(v) => {
              const key = v as ArchiveSortKey;
              setSortKey(key);
              setSortDir(key === "size" ? "desc" : "asc");
            }}
            options={ARCHIVE_SORT_OPTIONS}
            sortDir={sortDir}
            onSortDirChange={setSortDir}
          />
          <span className="text-xs text-text-muted">
            {filtered.length} archive{filtered.length !== 1 ? "s" : ""}
          </span>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => openPath(`${installPath}/downloaded_mods`).catch(() => {})}
            title="Open downloaded_mods folder in file explorer"
          >
            <FolderOpen size={14} /> Open Folder
          </Button>
          {orphanCount > 0 && !confirmCleanup && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setConfirmCleanup(true)}
              title={`Delete ${orphanCount} archive${orphanCount !== 1 ? "s" : ""} not linked to any installed mod`}
            >
              <Trash2 size={14} /> Clean {orphanCount} Orphan{orphanCount !== 1 ? "s" : ""}
            </Button>
          )}
          {confirmCleanup && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-danger">Delete {orphanCount} archive{orphanCount !== 1 ? "s" : ""}?</span>
              <Button
                variant="danger"
                size="sm"
                onClick={() => { cleanupOrphans.mutate(gameName); setConfirmCleanup(false); }}
                loading={cleanupOrphans.isPending}
              >
                Confirm
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmCleanup(false)}>
                Cancel
              </Button>
            </div>
          )}
        </div>

        <VirtualTable
          items={filtered}
          renderHead={() => (
            <tr className="sticky top-0 z-10 border-b border-border bg-surface-0 text-left text-text-muted text-xs">
              <th className="py-2 pr-2 w-8">
                <input
                  type="checkbox"
                  checked={bulk.isAllSelected}
                  onChange={() => bulk.isAllSelected ? bulk.deselectAll() : bulk.selectAll()}
                  className="rounded border-border accent-accent"
                />
              </th>
              <th className="py-2 pr-3">Archive</th>
              <th className="py-2 pr-3">Parsed Name</th>
              <th className="py-2 pr-3 whitespace-nowrap">Version</th>
              <th className="py-2 pr-3 whitespace-nowrap">Size</th>
              <th className="py-2 pr-3 whitespace-nowrap">Nexus ID</th>
              <th className="py-2 pr-3 whitespace-nowrap">Downloaded</th>
              <th className="py-2 pr-2 whitespace-nowrap">Status</th>
              <th className="py-2 pl-2 text-right whitespace-nowrap">Actions</th>
            </tr>
          )}
          renderRow={(a) => (
            <tr
              className="border-b border-border/50 hover:bg-surface-1/50 transition-colors"
              onContextMenu={(e) => openMenu(e, a)}
            >
              <td className="py-2 pr-2">
                <input
                  type="checkbox"
                  checked={bulk.isSelected(a.filename)}
                  onChange={() => bulk.toggle(a.filename)}
                  className="rounded border-border accent-accent"
                />
              </td>
              <td className="py-2 pr-3 font-mono text-xs text-text-primary max-w-[200px] truncate" title={a.filename}>
                {a.filename}
              </td>
              <td className="py-2 pr-3 text-text-secondary max-w-[180px] truncate" title={a.parsed_name}>
                {a.parsed_name}
              </td>
              <td className="py-2 pr-3 text-text-muted whitespace-nowrap">
                {a.parsed_version ?? "--"}
              </td>
              <td className={`py-2 pr-3 whitespace-nowrap ${a.is_empty ? "text-danger font-medium" : "text-text-muted"}`}>
                {formatBytes(a.size)}
              </td>
              <td className="py-2 pr-3 text-text-muted whitespace-nowrap">
                {a.nexus_mod_id ?? "--"}
              </td>
              <td className="py-2 pr-3 text-text-muted text-xs whitespace-nowrap">
                {a.last_downloaded_at ? timeAgo(isoToEpoch(a.last_downloaded_at)) : "--"}
              </td>
              <td className="py-2 pr-2 whitespace-nowrap">
                {a.is_empty ? (
                  <Badge variant="danger"><AlertTriangle size={10} /> Empty</Badge>
                ) : a.is_installed ? (
                  <Badge variant="success"><Check size={10} /> Installed</Badge>
                ) : (
                  <Badge variant="neutral">Orphan</Badge>
                )}
              </td>
              <td className="py-2 pl-2 whitespace-nowrap text-right">
                <div className="flex items-center justify-end gap-0.5">
                  {a.is_installed && a.installed_mod_id ? (
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => setConfirmUninstall({ filename: a.filename, modId: a.installed_mod_id! })}
                    >
                      <PackageMinus size={14} /> Uninstall
                    </Button>
                  ) : (
                    <div className="inline-flex items-center">
                      <button
                        disabled={a.is_empty || ((checkConflicts.isPending || installMod.isPending) && selectedArchive === a.filename)}
                        title={a.is_empty ? "Archive is empty — re-download from Nexus" : undefined}
                        onClick={() => handleCheckConflicts(a.filename)}
                        className="inline-flex items-center gap-1 rounded-l-md bg-accent px-2 py-1 text-xs font-medium text-white hover:opacity-80 disabled:opacity-50"
                      >
                        <Download size={14} /> Install
                      </button>
                      <button
                        disabled={a.is_empty}
                        onClick={(e) => {
                          if (splitMenuPos?.filename === a.filename) {
                            setSplitMenuPos(null);
                            return;
                          }
                          const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                          setSplitMenuPos({ top: rect.bottom + 4, left: rect.right - 160, filename: a.filename });
                        }}
                        className="inline-flex items-center self-stretch rounded-r-md border-l border-white/20 bg-accent px-1 text-xs font-medium text-white hover:opacity-80 disabled:opacity-50"
                        title="Install options"
                        aria-label="Install options"
                      >
                        <ChevronDown size={12} />
                      </button>
                    </div>
                  )}
                  {a.nexus_mod_id ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => window.open(`https://www.nexusmods.com/${gameDomain}/mods/${a.nexus_mod_id}?tab=files`, "_blank", "noopener,noreferrer")}
                      title={`View mod ${a.nexus_mod_id} on Nexus Mods`}
                      aria-label="View on Nexus"
                    >
                      <ExternalLink size={14} />
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                        setLinkPopover({ top: rect.bottom + 4, left: rect.right - 260, filename: a.filename });
                        setLinkInput("");
                      }}
                      title="Link to a Nexus mod"
                      aria-label="Link to Nexus"
                    >
                      <Link size={14} />
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setTreeFilename(a.filename)}
                    title="View archive contents"
                    aria-label="View contents"
                  >
                    <FolderTree size={14} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setConfirmDeleteFile(a.filename)}
                    title="Delete this archive file"
                    aria-label="Delete archive"
                  >
                    <Trash2 size={14} />
                  </Button>
                </div>
              </td>
            </tr>
          )}
        />

        {filtered.length === 0 && (filter || linkChip !== "all") && (
          <div className="py-4 text-sm text-text-muted text-center space-y-2">
            <p>No archives matching the current filters.</p>
            <button
              className="text-accent hover:text-accent-hover text-xs transition-colors"
              onClick={() => { setFilter(""); setLinkChip("all"); }}
            >
              Clear filters
            </button>
          </div>
        )}
      </div>

      <BulkActionBar
        selectedCount={bulk.selectedCount}
        totalCount={filtered.length}
        onSelectAll={bulk.selectAll}
        onDeselectAll={bulk.deselectAll}
        isAllSelected={bulk.isAllSelected}
      >
        <Button
          size="sm"
          loading={installMod.isPending || checkConflicts.isPending}
          onClick={handleBulkInstall}
        >
          <Download size={14} /> Install {bulk.selectedCount} Archive{bulk.selectedCount !== 1 ? "s" : ""}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setConfirmBulkDelete(true)}
        >
          <Trash2 size={14} /> Delete {bulk.selectedCount}
        </Button>
      </BulkActionBar>

      {queueProgress && (
        <div className="fixed bottom-16 left-1/2 -translate-x-1/2 z-40 rounded-lg border border-border bg-surface-1 px-4 py-3 shadow-lg min-w-[240px]">
          <div className="flex items-center justify-between text-sm text-text-primary mb-2">
            <span>
              {queueProgress.current === 0
                ? "Preparing install..."
                : `Installing ${queueProgress.current} of ${queueProgress.total}...`}
            </span>
            <span className="text-xs text-text-muted tabular-nums">
              {queueProgress.total > 0
                ? Math.round((queueProgress.current / queueProgress.total) * 100)
                : 0}%
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-surface-2 overflow-hidden">
            <div
              className="h-full rounded-full bg-accent transition-all duration-300"
              style={{ width: `${queueProgress.total > 0 ? (queueProgress.current / queueProgress.total) * 100 : 0}%` }}
            />
          </div>
        </div>
      )}

      {menuState.visible && menuState.data && (
        <ContextMenu
          items={buildContextItems(menuState.data)}
          position={menuState.position}
          onSelect={handleContextMenuSelect}
          onClose={closeMenu}
        />
      )}

      {confirmDeleteFile && (
        <ConfirmDialog
          title="Delete Archive?"
          message={`Permanently delete "${confirmDeleteFile}"? This cannot be undone.`}
          confirmLabel="Delete"
          variant="danger"
          icon={Trash2}
          loading={deleteArchive.isPending}
          onConfirm={async () => {
            await deleteArchive.mutateAsync({ gameName, filename: confirmDeleteFile });
            setConfirmDeleteFile(null);
          }}
          onCancel={() => setConfirmDeleteFile(null)}
        />
      )}

      {confirmBulkDelete && (
        <ConfirmDialog
          title="Delete Archives?"
          message={`Permanently delete ${bulk.selectedCount} archive${bulk.selectedCount !== 1 ? "s" : ""}? This cannot be undone.`}
          confirmLabel="Delete"
          variant="danger"
          icon={Trash2}
          loading={deleteArchive.isPending}
          onConfirm={async () => {
            const filenames = [...bulk.selectedIds];
            for (const filename of filenames) {
              await deleteArchive.mutateAsync({ gameName, filename });
            }
            bulk.deselectAll();
            setConfirmBulkDelete(false);
          }}
          onCancel={() => setConfirmBulkDelete(false)}
        />
      )}

      {confirmUninstall && (
        <ConfirmDialog
          title="Uninstall Mod?"
          message={`Uninstall the mod installed from "${confirmUninstall.filename}"? Mod files will be removed from the game directory.`}
          confirmLabel="Uninstall"
          variant="danger"
          icon={PackageMinus}
          loading={uninstallMod.isPending}
          onConfirm={async () => {
            await uninstallMod.mutateAsync({ gameName, modId: confirmUninstall.modId });
            setConfirmUninstall(null);
          }}
          onCancel={() => setConfirmUninstall(null)}
        />
      )}

      {fomodArchive && (
        <FomodWizard
          gameName={gameName}
          archiveFilename={fomodArchive}
          onDismiss={() => setFomodArchive(null)}
          onInstallComplete={() => setFomodArchive(null)}
        />
      )}

      {treeFilename && (
        <ArchiveTreeModal
          gameName={gameName}
          filename={treeFilename}
          onClose={() => setTreeFilename(null)}
        />
      )}

      {previewFilename && (
        <PreInstallPreview
          gameName={gameName}
          archiveFilename={previewFilename}
          onConfirm={handleInstallWithRenames}
          onCancel={() => setPreviewFilename(null)}
        />
      )}

      {conflicts && (
        <ConflictDialog
          conflicts={conflicts}
          onCancel={() => {
            setConflicts(null);
            setSelectedArchive(null);
            processNextInQueue();
          }}
          onSkip={handleInstallWithSkip}
          onOverwrite={handleInstallOverwrite}
        />
      )}

      {splitMenuPos && createPortal(
        <div
          ref={splitMenuRef}
          className="fixed z-50 min-w-[160px] rounded-md border border-border bg-surface-1 py-1 shadow-lg"
          style={{ top: splitMenuPos.top, left: splitMenuPos.left }}
        >
          <button
            onClick={() => {
              setPreviewFilename(splitMenuPos.filename);
              setSplitMenuPos(null);
            }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-text-secondary hover:bg-surface-2 hover:text-text-primary"
          >
            <Settings2 size={12} />
            Install with Options
          </button>
        </div>,
        document.body,
      )}

      {linkPopover && createPortal(
        <div
          ref={linkPopoverRef}
          className="fixed z-50 w-[260px] rounded-md border border-border bg-surface-1 p-3 shadow-lg"
          style={{ top: linkPopover.top, left: linkPopover.left }}
        >
          <p className="text-xs text-text-muted mb-2">Enter a Nexus mod ID or URL</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const value = linkInput.trim();
              if (!value) return;
              const urlMatch = value.match(/nexusmods\.com\/[^/]+\/mods\/(\d+)/);
              const modId = urlMatch ? parseInt(urlMatch[1], 10) : parseInt(value, 10);
              if (!modId || isNaN(modId)) {
                toast.error("Invalid mod ID", "Enter a number or a Nexus Mods URL");
                return;
              }
              linkArchive.mutate({ gameName, filename: linkPopover.filename, nexusModId: modId });
              setLinkPopover(null);
              setLinkInput("");
            }}
            className="flex gap-1.5"
          >
            <input
              type="text"
              value={linkInput}
              onChange={(e) => setLinkInput(e.target.value)}
              placeholder="e.g. 1234 or nexusmods.com/..."
              className="flex-1 rounded border border-border bg-surface-0 px-2 py-1 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent"
              autoFocus
            />
            <Button type="submit" size="sm" loading={linkArchive.isPending}>
              Link
            </Button>
          </form>
        </div>,
        document.body,
      )}
    </>
  );
}
