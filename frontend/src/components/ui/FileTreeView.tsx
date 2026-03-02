import {
  ChevronDown,
  ChevronRight,
  File,
  Folder,
  FolderOpen,
} from "lucide-react";
import { useState } from "react";

import { formatBytes } from "@/lib/format";
import type { ArchiveEntryNode } from "@/types/api";

function TreeNode({ node, depth, showSize = true }: { node: ArchiveEntryNode; depth: number; showSize?: boolean }) {
  const [open, setOpen] = useState(true);

  if (!node.is_dir) {
    return (
      <div
        className="flex items-center gap-1.5 py-0.5 hover:bg-surface-2/50 rounded pr-2"
        style={{ paddingLeft: `${depth * 1.25}rem` }}
      >
        <File size={14} className="shrink-0 text-text-muted" />
        <span className="font-mono text-xs text-text-secondary truncate">
          {node.name}
        </span>
        {showSize && (
          <span className="ml-auto font-mono text-xs text-text-muted whitespace-nowrap">
            {formatBytes(node.size)}
          </span>
        )}
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        className="flex w-full items-center gap-1.5 py-0.5 hover:bg-surface-2/50 rounded pr-2 text-left"
        style={{ paddingLeft: `${depth * 1.25}rem` }}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ChevronDown size={14} className="shrink-0 text-text-muted" />
        ) : (
          <ChevronRight size={14} className="shrink-0 text-text-muted" />
        )}
        {open ? (
          <FolderOpen size={14} className="shrink-0 text-accent" />
        ) : (
          <Folder size={14} className="shrink-0 text-accent" />
        )}
        <span className="font-mono text-xs text-text-primary truncate">
          {node.name}
        </span>
      </button>
      {open &&
        node.children.map((child) => (
          <TreeNode key={child.name} node={child} depth={depth + 1} showSize={showSize} />
        ))}
    </div>
  );
}

export function FileTreeView({ tree, showSize = true }: { tree: ArchiveEntryNode[]; showSize?: boolean }) {
  return (
    <>
      {tree.map((node) => (
        <TreeNode key={node.name} node={node} depth={0} showSize={showSize} />
      ))}
    </>
  );
}
