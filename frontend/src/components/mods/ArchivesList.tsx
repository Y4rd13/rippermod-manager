import { AlertTriangle, Archive, Copy, Download, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { BulkActionBar } from "@/components/ui/BulkActionBar";
import { ContextMenu, type ContextMenuItem } from "@/components/ui/ContextMenu";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { SkeletonTable } from "@/components/ui/SkeletonTable";
import {
  useCheckConflicts,
  useInstallMod,
} from "@/hooks/mutations";
import { useBulkSelect } from "@/hooks/use-bulk-select";
import { useContextMenu } from "@/hooks/use-context-menu";
import { formatBytes } from "@/lib/format";
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

type LinkChip = "all" | "linked" | "unlinked";

const ARCHIVE_SORT_OPTIONS: { value: ArchiveSortKey; label: string }[] = [
  { value: "name", label: "Name" },
  { value: "size", label: "Size" },
  { value: "version", label: "Version" },
];

const ROW_CONTEXT_ITEMS: ContextMenuItem[] = [
  { key: "install", label: "Install", icon: Download },
  { key: "copy", label: "Copy Filename", icon: Copy },
];

export function ArchivesList({ archives, gameName, isLoading }: Props) {
  const installMod = useInstallMod();
  const checkConflicts = useCheckConflicts();
  const [conflicts, setConflicts] = useState<ConflictCheckResult | null>(null);
  const [selectedArchive, setSelectedArchive] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<ArchiveSortKey>("name");
  const [linkChip, setLinkChip] = useState<LinkChip>("all");

  const { menuState, openMenu, closeMenu } = useContextMenu<AvailableArchive>();

  const filtered = useMemo(() => {
    const q = filter.toLowerCase();
    const items = archives.filter((a) => {
      if (linkChip === "linked" && a.nexus_mod_id == null) return false;
      if (linkChip === "unlinked" && a.nexus_mod_id != null) return false;
      if (!q) return true;
      return (
        a.filename.toLowerCase().includes(q) ||
        a.parsed_name.toLowerCase().includes(q)
      );
    });

    items.sort((a, b) => {
      switch (sortKey) {
        case "name":
          return a.parsed_name.localeCompare(b.parsed_name);
        case "size":
          return b.size - a.size;
        case "version":
          return (a.parsed_version ?? "").localeCompare(b.parsed_version ?? "", undefined, { numeric: true });
      }
    });

    return items;
  }, [archives, filter, sortKey, linkChip]);

  const bulk = useBulkSelect(filtered.map((a) => a.filename));

  const linkedCount = useMemo(
    () => archives.filter((a) => a.nexus_mod_id != null).length,
    [archives],
  );

  const unlinkedCount = useMemo(
    () => archives.filter((a) => a.nexus_mod_id == null).length,
    [archives],
  );

  const filterChips = [
    { key: "all", label: "All", count: archives.length },
    { key: "linked", label: "Linked", count: linkedCount },
    { key: "unlinked", label: "Unlinked", count: unlinkedCount },
  ];

  const installQueueRef = useRef<string[]>([]);

  const processNextInQueue = () => {
    if (installQueueRef.current.length === 0) return;
    const next = installQueueRef.current.shift()!;
    handleCheckConflicts(next);
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
    installQueueRef.current = [...bulk.selectedIds];
    bulk.deselectAll();
    processNextInQueue();
  };

  const handleContextMenuSelect = (key: string) => {
    const archive = menuState.data;
    if (!archive) return;
    if (key === "install") {
      handleCheckConflicts(archive.filename);
    } else if (key === "copy") {
      navigator.clipboard.writeText(archive.filename);
    }
  };

  useEffect(() => {
    if (!conflicts) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setConflicts(null);
        setSelectedArchive(null);
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
          <div className="relative flex-1 max-w-xs">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              placeholder="Filter by filename..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-full rounded-lg border border-border bg-surface-2 py-1.5 pl-8 pr-3 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as ArchiveSortKey)}
            className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
          >
            {ARCHIVE_SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <span className="text-xs text-text-muted">
            {filtered.length} archive{filtered.length !== 1 ? "s" : ""}
          </span>
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
                <th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((a) => (
                <tr
                  key={a.filename}
                  className="border-b border-border/50"
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
                  <td className="py-2 pr-4 font-mono text-xs text-text-primary max-w-[200px] truncate">
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
                  <td className="py-2 text-right">
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
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {filtered.length === 0 && (filter || linkChip !== "all") && (
          <p className="py-4 text-sm text-text-muted">
            No archives matching the current filters.
          </p>
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
      </BulkActionBar>

      {menuState.visible && menuState.data && (
        <ContextMenu
          items={ROW_CONTEXT_ITEMS}
          position={menuState.position}
          onSelect={handleContextMenuSelect}
          onClose={closeMenu}
        />
      )}

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
                  <span className="font-mono text-text-primary">
                    {c.file_path}
                  </span>
                  <span className="ml-2 text-text-muted">
                    (owned by {c.owning_mod_name})
                  </span>
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setConflicts(null);
                  setSelectedArchive(null);
                }}
              >
                Cancel
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleInstallWithSkip}
              >
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
