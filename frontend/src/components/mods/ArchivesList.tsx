import { Archive, Check, Copy, Download, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { ConflictDialog } from "@/components/mods/ConflictDialog";
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
import {
  useCheckConflicts,
  useCleanupOrphans,
  useDeleteArchive,
  useInstallMod,
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
  isLoading?: boolean;
}

type ArchiveSortKey = "name" | "size" | "version";

type LinkChip = "all" | "linked" | "unlinked" | "installed" | "orphan";

const ARCHIVE_SORT_OPTIONS: { value: ArchiveSortKey; label: string }[] = [
  { value: "name", label: "Name" },
  { value: "size", label: "Size" },
  { value: "version", label: "Version" },
];

const ROW_CONTEXT_ITEMS: ContextMenuItem[] = [
  { key: "install", label: "Install", icon: Download },
  { key: "copy", label: "Copy Filename", icon: Copy },
  { key: "delete", label: "Delete Archive", icon: Trash2, variant: "danger" },
];

export function ArchivesList({ archives, gameName, isLoading }: Props) {
  const installMod = useInstallMod();
  const checkConflicts = useCheckConflicts();
  const deleteArchive = useDeleteArchive();
  const cleanupOrphans = useCleanupOrphans();
  const [conflicts, setConflicts] = useState<ConflictCheckResult | null>(null);
  const [selectedArchive, setSelectedArchive] = useState<string | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [confirmDeleteFile, setConfirmDeleteFile] = useState<string | null>(null);
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
      data: { archive_filename: conflicts.archive_filename, skip_conflicts: conflicts.conflicts.map((c) => c.file_path) },
    });
    setConflicts(null);
    setSelectedArchive(null);
    processNextInQueue();
  };

  const handleInstallOverwrite = () => {
    if (!conflicts) return;
    installMod.mutate({ gameName, data: { archive_filename: conflicts.archive_filename, skip_conflicts: [] } });
    setConflicts(null);
    setSelectedArchive(null);
    processNextInQueue();
  };

  const handleBulkInstall = () => {
    const items = [...bulk.selectedIds];
    installQueueRef.current = items;
    setQueueProgress({ current: 0, total: items.length });
    bulk.deselectAll();
    processNextInQueue();
  };

  const handleContextMenuSelect = (key: string) => {
    const archive = menuState.data;
    if (!archive) return;
    if (key === "install") {
      handleCheckConflicts(archive.filename);
    } else if (key === "copy") {
      void navigator.clipboard.writeText(archive.filename).then(
        () => toast.success("Copied to clipboard"),
        () => toast.error("Failed to copy"),
      );
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

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="sticky top-0 z-10 border-b border-border bg-surface-0 text-left text-text-muted">
                <th className="py-2 pr-4 w-8">
                  <input
                    type="checkbox"
                    checked={bulk.isAllSelected}
                    onChange={() => bulk.isAllSelected ? bulk.deselectAll() : bulk.selectAll()}
                    className="rounded border-border accent-accent"
                  />
                </th>
                <th className="py-2 pr-4">Archive</th>
                <th className="py-2 pr-4">Parsed Name</th>
                <th className="py-2 pr-4">Version</th>
                <th className="py-2 pr-4">Size</th>
                <th className="py-2 pr-4">Nexus ID</th>
                <th className="py-2 pr-4">Downloaded</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((a) => (
                <tr
                  key={a.filename}
                  className="border-b border-border/50 hover:bg-surface-1/50 transition-colors"
                  onContextMenu={(e) => openMenu(e, a)}
                >
                  <td className="py-2 pr-4">
                    <input
                      type="checkbox"
                      checked={bulk.isSelected(a.filename)}
                      onChange={() => bulk.toggle(a.filename)}
                      className="rounded border-border accent-accent"
                    />
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-text-primary max-w-[200px] truncate" title={a.filename}>
                    {a.filename}
                  </td>
                  <td className="py-2 pr-4 text-text-secondary">
                    {a.parsed_name}
                  </td>
                  <td className="py-2 pr-4 text-text-muted">
                    {a.parsed_version ?? "--"}
                  </td>
                  <td className="py-2 pr-4 text-text-muted">
                    {formatBytes(a.size)}
                  </td>
                  <td className="py-2 pr-4 text-text-muted">
                    {a.nexus_mod_id ?? "--"}
                  </td>
                  <td className="py-2 pr-4 text-text-muted text-xs">
                    {a.last_downloaded_at ? timeAgo(isoToEpoch(a.last_downloaded_at)) : "--"}
                  </td>
                  <td className="py-2 pr-4">
                    {a.is_installed ? (
                      <Badge variant="success"><Check size={10} /> Installed</Badge>
                    ) : (
                      <Badge variant="neutral">Orphan</Badge>
                    )}
                  </td>
                  <td className="py-2 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        size="sm"
                        loading={
                          (checkConflicts.isPending || installMod.isPending) &&
                          selectedArchive === a.filename
                        }
                        onClick={() => handleCheckConflicts(a.filename)}
                      >
                        <Download size={14} /> Install
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
              ))}
            </tbody>
          </table>
        </div>

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
          loading={deleteArchive.isPending}
          onClick={async () => {
            const filenames = [...bulk.selectedIds];
            for (const filename of filenames) {
              await deleteArchive.mutateAsync({ gameName, filename });
            }
            bulk.deselectAll();
          }}
        >
          <Trash2 size={14} /> Delete {bulk.selectedCount}
        </Button>
      </BulkActionBar>

      {queueProgress && (
        <div className="fixed bottom-16 left-1/2 -translate-x-1/2 z-40 rounded-lg border border-border bg-surface-1 px-4 py-3 shadow-lg min-w-[240px]">
          <div className="flex items-center justify-between text-sm text-text-primary mb-2">
            <span>Installing {queueProgress.current} of {queueProgress.total}...</span>
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
          items={ROW_CONTEXT_ITEMS}
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
          onConfirm={() => {
            deleteArchive.mutate({ gameName, filename: confirmDeleteFile });
            setConfirmDeleteFile(null);
          }}
          onCancel={() => setConfirmDeleteFile(null)}
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
    </>
  );
}
