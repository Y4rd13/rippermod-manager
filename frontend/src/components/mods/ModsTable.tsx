import { ChevronDown, ChevronUp, Copy, ExternalLink, FileText } from "lucide-react";
import { Fragment, useMemo, useState } from "react";

import { ContextMenu, type ContextMenuItem } from "@/components/ui/ContextMenu";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { SearchInput } from "@/components/ui/SearchInput";
import { SkeletonTable } from "@/components/ui/SkeletonTable";
import { ConfidenceBadge } from "@/components/ui/Badge";
import { formatBytes } from "@/lib/format";
import type { ModGroup } from "@/types/api";
import { useContextMenu } from "@/hooks/use-context-menu";
import { useSessionState } from "@/hooks/use-session-state";
import { toast } from "@/stores/toast-store";

type SortKey = "name" | "files" | "confidence" | "match";
type SortDir = "asc" | "desc";
type MatchFilter = "all" | "matched" | "unmatched";

function SortIcon({ col, sortKey, sortDir }: { col: SortKey; sortKey: SortKey; sortDir: SortDir }) {
  if (sortKey !== col) return null;
  return sortDir === "asc" ? <ChevronUp size={14} /> : <ChevronDown size={14} />;
}

export function ModsTable({ mods, isLoading }: { mods: ModGroup[]; isLoading?: boolean }) {
  const [sortKey, setSortKey] = useSessionState<SortKey>("mods-sort", "name");
  const [sortDir, setSortDir] = useSessionState<SortDir>("mods-dir", "asc");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState("");
  const [matchFilter, setMatchFilter] = useSessionState<MatchFilter>("mods-chip", "all");

  const { menuState, openMenu, closeMenu } = useContextMenu<ModGroup>();

  const matchedCount = useMemo(() => mods.filter((m) => m.nexus_match != null).length, [mods]);
  const unmatchedCount = mods.length - matchedCount;

  const filterChips = [
    { key: "all", label: "All", count: mods.length },
    { key: "matched", label: "Matched", count: matchedCount },
    { key: "unmatched", label: "Unmatched", count: unmatchedCount },
  ];

  const filtered = useMemo(() => {
    const q = filter.toLowerCase();
    const items = mods.filter((m) => {
      // Apply match filter chip.
      if (matchFilter === "matched" && m.nexus_match == null) return false;
      if (matchFilter === "unmatched" && m.nexus_match != null) return false;

      // Apply text search filter.
      if (!q) return true;
      return (
        m.display_name.toLowerCase().includes(q) ||
        (m.nexus_match?.mod_name.toLowerCase().includes(q) ?? false)
      );
    });

    items.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "name":
          cmp = a.display_name.localeCompare(b.display_name);
          break;
        case "files":
          cmp = a.files.length - b.files.length;
          break;
        case "confidence":
          cmp = a.confidence - b.confidence;
          break;
        case "match":
          cmp = (a.nexus_match?.score ?? 0) - (b.nexus_match?.score ?? 0);
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });

    return items;
  }, [mods, filter, matchFilter, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const toggleExpand = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const buildContextMenuItems = (mod: ModGroup): ContextMenuItem[] => [
    {
      key: "copy-name",
      label: "Copy Name",
      icon: Copy,
    },
    {
      key: "separator",
      label: "",
      separator: true,
    },
    {
      key: "expand",
      label: expanded.has(mod.id) ? "Collapse" : "Expand",
      icon: expanded.has(mod.id) ? ChevronUp : ChevronDown,
    },
  ];

  const handleContextMenuSelect = (key: string) => {
    const mod = menuState.data;
    if (!mod) return;

    switch (key) {
      case "copy-name":
        void navigator.clipboard.writeText(mod.display_name).then(
          () => toast.success("Copied to clipboard"),
          () => toast.error("Failed to copy"),
        );
        break;
      case "expand":
        toggleExpand(mod.id);
        break;
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <SkeletonTable columns={5} rows={6} />
      </div>
    );
  }

  if (mods.length === 0) {
    return (
      <EmptyState
        icon={Search}
        title="No Scanned Mods"
        description="Run a scan to discover local mods in your game directory."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <FilterChips
          chips={filterChips}
          active={matchFilter}
          onChange={(key) => setMatchFilter(key as MatchFilter)}
        />

        <SearchInput value={filter} onChange={setFilter} placeholder="Filter by name or match..." className="ml-auto" />

        <span className="text-xs text-text-muted">
          {filtered.length} mod{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="sticky top-0 z-10 bg-surface-0 border-b border-border text-left">
              <th className="py-2 pr-4 w-6" />
              <th
                className="py-2 pr-4 cursor-pointer select-none text-text-muted hover:text-text-primary"
                onClick={() => toggleSort("name")}
              >
                <span className="flex items-center gap-1">
                  Mod Name <SortIcon col="name" sortKey={sortKey} sortDir={sortDir} />
                </span>
              </th>
              <th
                className="py-2 pr-4 cursor-pointer select-none text-text-muted hover:text-text-primary"
                onClick={() => toggleSort("files")}
              >
                <span className="flex items-center gap-1">
                  Files <SortIcon col="files" sortKey={sortKey} sortDir={sortDir} />
                </span>
              </th>
              <th
                className="py-2 pr-4 cursor-pointer select-none text-text-muted hover:text-text-primary"
                onClick={() => toggleSort("match")}
              >
                <span className="flex items-center gap-1">
                  Nexus Match <SortIcon col="match" sortKey={sortKey} sortDir={sortDir} />
                </span>
              </th>
              <th
                className="py-2 pr-4 cursor-pointer select-none text-text-muted hover:text-text-primary"
                onClick={() => toggleSort("confidence")}
              >
                <span className="flex items-center gap-1" title="How tightly the files in this mod group cluster together">
                  Cluster <SortIcon col="confidence" sortKey={sortKey} sortDir={sortDir} />
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((mod) => (
              <Fragment key={mod.id}>
                <tr
                  className="border-b border-border/50 hover:bg-surface-1/50 cursor-pointer"
                  onClick={() => toggleExpand(mod.id)}
                  onContextMenu={(e) => openMenu(e, mod)}
                >
                  <td className="py-2 pr-2">
                    {expanded.has(mod.id) ? (
                      <ChevronDown size={14} className="text-text-muted" />
                    ) : (
                      <FileText size={14} className="text-text-muted" />
                    )}
                  </td>
                  <td className="py-2 pr-4 text-text-primary font-medium">{mod.display_name}</td>
                  <td className="py-2 pr-4 text-text-muted">{mod.files.length}</td>
                  <td className="py-2 pr-4">
                    {mod.nexus_match ? (
                      <div className="flex items-center gap-2">
                        <ConfidenceBadge score={mod.nexus_match.score} />
                        <span className="text-text-secondary text-xs truncate max-w-[200px]">
                          {mod.nexus_match.mod_name}
                        </span>
                      </div>
                    ) : (
                      <span className="text-text-muted text-xs">No match</span>
                    )}
                  </td>
                  <td className="py-2 pr-4">
                    <ConfidenceBadge score={mod.confidence} />
                  </td>
                </tr>
                {expanded.has(mod.id) && (
                  <tr key={`${mod.id}-detail`}>
                    <td colSpan={5} className="pb-3 pt-1 px-8">
                      <div className="rounded-lg bg-surface-2 p-3 space-y-1">
                        {mod.files.map((f) => (
                          <div key={f.id} className="flex items-center justify-between text-xs">
                            <span className="text-text-secondary font-mono truncate max-w-[400px]">
                              {f.file_path}
                            </span>
                            <span className="text-text-muted">{formatBytes(f.file_size)}</span>
                          </div>
                        ))}
                        {mod.nexus_match && (
                          <div className="mt-2 pt-2 border-t border-border flex items-center gap-2 text-xs">
                            <ExternalLink size={12} className="text-accent" />
                            <span className="text-text-muted">
                              Matched via {mod.nexus_match.method} — Nexus Mod #
                              {mod.nexus_match.nexus_mod_id}
                            </span>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {filtered.length === 0 && (filter || matchFilter !== "all") && (
        <div className="py-4 text-sm text-text-muted text-center space-y-2">
          <p>
            No mods matching the current filter
            {filter ? <> &quot;{filter}&quot;</> : ""}.
          </p>
          <button
            className="text-accent hover:text-accent-hover text-xs transition-colors"
            onClick={() => { setFilter(""); setMatchFilter("all"); }}
          >
            Clear filters
          </button>
        </div>
      )}

      {menuState.visible && menuState.data && (
        <ContextMenu
          items={buildContextMenuItems(menuState.data)}
          position={menuState.position}
          onSelect={handleContextMenuSelect}
          onClose={closeMenu}
        />
      )}
    </div>
  );
}
