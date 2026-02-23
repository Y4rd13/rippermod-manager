import { Download, ExternalLink, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";

import { SourceBadge } from "@/components/mods/SourceBadge";
import { UpdateDownloadCell } from "@/components/mods/UpdateDownloadCell";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { SearchInput } from "@/components/ui/SearchInput";
import { SkeletonTable } from "@/components/ui/SkeletonTable";
import { SortSelect } from "@/components/ui/SortSelect";
import { openUrl } from "@tauri-apps/plugin-opener";

import { useCheckUpdates, useStartDownload } from "@/hooks/mutations";
import { useDownloadJobs } from "@/hooks/queries";
import { useSessionState } from "@/hooks/use-session-state";
import { timeAgo } from "@/lib/format";
import type { ModUpdate } from "@/types/api";

type UpdateSortKey = "name" | "author" | "source" | "updated";

const UPDATE_SORT_OPTIONS: { value: UpdateSortKey; label: string }[] = [
  { value: "name", label: "Name" },
  { value: "author", label: "Author" },
  { value: "source", label: "Source" },
  { value: "updated", label: "Last Updated" },
];

interface Props {
  gameName: string;
  updates: ModUpdate[];
  isLoading?: boolean;
}

export function UpdatesTable({ gameName, updates, isLoading }: Props) {
  const { data: downloadJobs = [] } = useDownloadJobs(gameName);
  const checkUpdates = useCheckUpdates();
  const startDownload = useStartDownload();
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useSessionState<UpdateSortKey>(`updates-sort-${gameName}`, "updated");
  const [sortDir, setSortDir] = useSessionState<"asc" | "desc">(`updates-dir-${gameName}`, "desc");
  const [chip, setChip] = useSessionState(`updates-chip-${gameName}`, "all");

  const filteredUpdates = useMemo(() => {
    const q = filter.toLowerCase();
    const items = updates.filter((u) => {
      if (q && !u.display_name.toLowerCase().includes(q) && !u.author.toLowerCase().includes(q)) return false;
      if (chip !== "all" && u.source !== chip) return false;
      return true;
    });

    items.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "name":
          cmp = a.display_name.localeCompare(b.display_name);
          break;
        case "author":
          cmp = a.author.localeCompare(b.author);
          break;
        case "source":
          cmp = a.source.localeCompare(b.source);
          break;
        case "updated":
          cmp = (a.nexus_timestamp ?? 0) - (b.nexus_timestamp ?? 0);
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });

    return items;
  }, [updates, filter, sortKey, sortDir, chip]);

  const downloadableUpdates = filteredUpdates.filter((u) => u.nexus_file_id != null);

  const handleUpdateAll = async () => {
    for (const u of downloadableUpdates) {
      if (u.nexus_file_id) {
        try {
          await startDownload.mutateAsync({
            gameName,
            data: {
              nexus_mod_id: u.nexus_mod_id,
              nexus_file_id: u.nexus_file_id,
            },
          });
        } catch {
          // Individual download errors handled by mutation callbacks
        }
      }
    }
  };

  const updateChips = useMemo(() => {
    const sources = new Set(updates.map((u) => u.source));
    const chips = [{ key: "all", label: "All" }];
    if (sources.has("installed")) chips.push({ key: "installed", label: "Installed" });
    if (sources.has("correlation")) chips.push({ key: "correlation", label: "Matched" });
    if (sources.has("endorsed")) chips.push({ key: "endorsed", label: "Endorsed" });
    if (sources.has("tracked")) chips.push({ key: "tracked", label: "Tracked" });
    return chips;
  }, [updates]);

  if (isLoading) return <SkeletonTable columns={8} rows={5} />;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <SearchInput value={filter} onChange={setFilter} placeholder="Filter by name or author..." />
        <SortSelect
          value={sortKey}
          onChange={(v) => setSortKey(v as UpdateSortKey)}
          options={UPDATE_SORT_OPTIONS}
          sortDir={sortDir}
          onSortDirChange={setSortDir}
        />
        <span className="text-xs text-text-muted">
          {filteredUpdates.length} update{filteredUpdates.length !== 1 ? "s" : ""}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {downloadableUpdates.length > 1 && (
            <Button
              variant="secondary"
              size="sm"
              onClick={handleUpdateAll}
              loading={startDownload.isPending}
              title="Download all available updates from Nexus"
            >
              <Download className="h-3.5 w-3.5 mr-1" />
              Update All ({downloadableUpdates.length})
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => checkUpdates.mutate(gameName)}
            loading={checkUpdates.isPending}
            title="Check Nexus for newer versions of your mods"
          >
            <RefreshCw className="h-3.5 w-3.5 mr-1" />
            Check Now
          </Button>
        </div>
      </div>

      {updateChips.length > 2 && (
        <FilterChips chips={updateChips} active={chip} onChange={setChip} />
      )}

      {!updates.length ? (
        <EmptyState
          icon={RefreshCw}
          title="No Updates Found"
          description="Run a scan first, then check for updates to find newer versions of your mods."
          actions={
            <Button
              size="sm"
              onClick={() => checkUpdates.mutate(gameName)}
              loading={checkUpdates.isPending}
            >
              Check Now
            </Button>
          }
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text-muted sticky top-0 z-10 bg-surface-0">
                <th className="py-2 pr-4">Mod</th>
                <th className="py-2 pr-4">Local Version</th>
                <th className="py-2 pr-4">Nexus Version</th>
                <th className="py-2 pr-4">Source</th>
                <th className="py-2 pr-4">Author</th>
                <th className="py-2 pr-4">Updated</th>
                <th className="py-2 pr-4">Downloaded</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {filteredUpdates.map((u, i) => (
                <tr
                  key={u.installed_mod_id ?? `group-${u.mod_group_id ?? i}`}
                  className="border-b border-border/50 hover:bg-surface-1/50 transition-colors"
                >
                  <td className="py-2 pr-4 text-text-primary">
                    <div className="flex items-center gap-1.5">
                      <span>{u.display_name}</span>
                      {u.nexus_url && (
                        <button
                          onClick={() => openUrl(u.nexus_url).catch(() => {})}
                          title="Open mod page on Nexus Mods"
                          aria-label="Open on Nexus Mods"
                          className="text-text-muted hover:text-accent shrink-0"
                        >
                          <ExternalLink size={12} />
                        </button>
                      )}
                    </div>
                  </td>
                  <td className="py-2 pr-4 text-text-muted">{u.local_version}</td>
                  <td className="py-2 pr-4 text-success font-medium">{u.nexus_version}</td>
                  <td className="py-2 pr-4">
                    <SourceBadge source={u.source} />
                  </td>
                  <td className="py-2 pr-4 text-text-muted">{u.author}</td>
                  <td className="py-2 pr-4 text-text-muted">
                    {u.nexus_timestamp ? timeAgo(u.nexus_timestamp) : "\u2014"}
                  </td>
                  <td className="py-2 pr-4 text-text-muted text-xs">
                    {u.local_download_date ? timeAgo(u.local_download_date) : "\u2014"}
                  </td>
                  <td className="py-2">
                    <UpdateDownloadCell
                      update={u}
                      gameName={gameName}
                      downloadJobs={downloadJobs}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
