import { ChevronDown, ChevronUp, ExternalLink, FileText, Search } from "lucide-react";
import { Fragment, useMemo, useState } from "react";

import { ConfidenceBadge } from "@/components/ui/Badge";
import { formatBytes } from "@/lib/format";
import type { ModGroup } from "@/types/api";

type SortKey = "name" | "files" | "confidence" | "match";
type SortDir = "asc" | "desc";

function SortIcon({ col, sortKey, sortDir }: { col: SortKey; sortKey: SortKey; sortDir: SortDir }) {
  if (sortKey !== col) return null;
  return sortDir === "asc" ? (
    <ChevronUp size={14} />
  ) : (
    <ChevronDown size={14} />
  );
}

export function ModsTable({ mods }: { mods: ModGroup[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState("");

  const filtered = useMemo(() => {
    const q = filter.toLowerCase();
    const items = mods.filter((m) => {
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
  }, [mods, filter, sortKey, sortDir]);

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

  if (mods.length === 0) {
    return (
      <p className="text-text-muted text-sm py-4">
        No mods found. Run a scan to discover local mods.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="Filter by name or match..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="w-full rounded-lg border border-border bg-surface-2 py-1.5 pl-8 pr-3 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
          />
        </div>
        <span className="text-xs text-text-muted">
          {filtered.length} mod{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="pb-2 pr-4 w-6" />
              <th
                className="pb-2 pr-4 cursor-pointer select-none text-text-muted hover:text-text-primary"
                onClick={() => toggleSort("name")}
              >
                <span className="flex items-center gap-1">
                  Mod Name <SortIcon col="name" sortKey={sortKey} sortDir={sortDir} />
                </span>
              </th>
              <th
                className="pb-2 pr-4 cursor-pointer select-none text-text-muted hover:text-text-primary"
                onClick={() => toggleSort("files")}
              >
                <span className="flex items-center gap-1">
                  Files <SortIcon col="files" sortKey={sortKey} sortDir={sortDir} />
                </span>
              </th>
              <th
                className="pb-2 pr-4 cursor-pointer select-none text-text-muted hover:text-text-primary"
                onClick={() => toggleSort("match")}
              >
                <span className="flex items-center gap-1">
                  Nexus Match <SortIcon col="match" sortKey={sortKey} sortDir={sortDir} />
                </span>
              </th>
              <th
                className="pb-2 pr-4 cursor-pointer select-none text-text-muted hover:text-text-primary"
                onClick={() => toggleSort("confidence")}
              >
                <span className="flex items-center gap-1">
                  Confidence <SortIcon col="confidence" sortKey={sortKey} sortDir={sortDir} />
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
                >
                  <td className="py-2 pr-2">
                    {expanded.has(mod.id) ? (
                      <ChevronDown size={14} className="text-text-muted" />
                    ) : (
                      <FileText size={14} className="text-text-muted" />
                    )}
                  </td>
                  <td className="py-2 pr-4 text-text-primary font-medium">
                    {mod.display_name}
                  </td>
                  <td className="py-2 pr-4 text-text-muted">
                    {mod.files.length}
                  </td>
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
                          <div
                            key={f.id}
                            className="flex items-center justify-between text-xs"
                          >
                            <span className="text-text-secondary font-mono truncate max-w-[400px]">
                              {f.file_path}
                            </span>
                            <span className="text-text-muted">
                              {formatBytes(f.file_size)}
                            </span>
                          </div>
                        ))}
                        {mod.nexus_match && (
                          <div className="mt-2 pt-2 border-t border-border flex items-center gap-2 text-xs">
                            <ExternalLink size={12} className="text-accent" />
                            <span className="text-text-muted">
                              Matched via {mod.nexus_match.method} — Nexus Mod #{mod.nexus_match.nexus_mod_id}
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

      {filtered.length === 0 && filter && (
        <p className="py-4 text-sm text-text-muted">
          No mods matching &quot;{filter}&quot;.
        </p>
      )}
    </div>
  );
}
