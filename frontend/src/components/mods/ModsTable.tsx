import { ChevronDown, ChevronUp, ExternalLink, FileText } from "lucide-react";
import { useMemo, useState } from "react";

import { ConfidenceBadge } from "@/components/ui/Badge";
import type { ModGroup } from "@/types/api";

type SortKey = "name" | "files" | "confidence" | "match";
type SortDir = "asc" | "desc";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function ModsTable({ mods }: { mods: ModGroup[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const sorted = useMemo(() => {
    const arr = [...mods];
    arr.sort((a, b) => {
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
    return arr;
  }, [mods, sortKey, sortDir]);

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

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return null;
    return sortDir === "asc" ? (
      <ChevronUp size={14} />
    ) : (
      <ChevronDown size={14} />
    );
  };

  if (mods.length === 0) {
    return (
      <p className="text-text-muted text-sm py-4">
        No mods found. Run a scan to discover local mods.
      </p>
    );
  }

  return (
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
                Mod Name <SortIcon col="name" />
              </span>
            </th>
            <th
              className="pb-2 pr-4 cursor-pointer select-none text-text-muted hover:text-text-primary"
              onClick={() => toggleSort("files")}
            >
              <span className="flex items-center gap-1">
                Files <SortIcon col="files" />
              </span>
            </th>
            <th
              className="pb-2 pr-4 cursor-pointer select-none text-text-muted hover:text-text-primary"
              onClick={() => toggleSort("match")}
            >
              <span className="flex items-center gap-1">
                Nexus Match <SortIcon col="match" />
              </span>
            </th>
            <th
              className="pb-2 pr-4 cursor-pointer select-none text-text-muted hover:text-text-primary"
              onClick={() => toggleSort("confidence")}
            >
              <span className="flex items-center gap-1">
                Confidence <SortIcon col="confidence" />
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((mod) => (
            <>
              <tr
                key={mod.id}
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
            </>
          ))}
        </tbody>
      </table>
    </div>
  );
}
