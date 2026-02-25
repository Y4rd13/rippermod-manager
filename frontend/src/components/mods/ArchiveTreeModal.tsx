import {
  ChevronDown,
  ChevronRight,
  File,
  Folder,
  FolderOpen,
  Loader2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useArchiveContents } from "@/hooks/queries";
import { formatBytes } from "@/lib/format";
import type { ArchiveEntryNode } from "@/types/api";

interface Props {
  gameName: string;
  filename: string;
  onClose: () => void;
}

function TreeNode({
  node,
  depth,
}: {
  node: ArchiveEntryNode;
  depth: number;
}) {
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
        <span className="ml-auto font-mono text-xs text-text-muted whitespace-nowrap">
          {formatBytes(node.size)}
        </span>
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
          <TreeNode
            key={child.name}
            node={child}
            depth={depth + 1}
          />
        ))}
    </div>
  );
}

export function ArchiveTreeModal({ gameName, filename, onClose }: Props) {
  const { data, isLoading, error } = useArchiveContents(gameName, filename);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="archive-tree-title"
        className="w-full max-w-2xl rounded-xl border border-border bg-surface-1 p-6 animate-modal-in"
      >
        <div className="mb-4 flex items-center justify-between">
          <div className="min-w-0 mr-4">
            <h3
              id="archive-tree-title"
              className="text-lg font-semibold text-text-primary truncate"
              title={filename}
            >
              {filename}
            </h3>
            {data && (
              <p className="text-xs text-text-muted mt-0.5">
                {data.total_files} file{data.total_files !== 1 ? "s" : ""}{" "}
                &middot; {formatBytes(data.total_size)}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary transition-colors"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto rounded border border-border bg-surface-0 p-3">
          {isLoading && (
            <div className="flex items-center justify-center py-8 text-text-muted">
              <Loader2 size={20} className="animate-spin mr-2" />
              <span className="text-sm">Loading archive contents...</span>
            </div>
          )}

          {error && (
            <p className="text-sm text-danger py-4 text-center">
              Failed to load archive contents.
            </p>
          )}

          {data &&
            data.tree.map((node) => (
              <TreeNode
                key={node.name}
                node={node}
                depth={0}
              />
            ))}

          {data && data.tree.length === 0 && (
            <p className="text-sm text-text-muted py-4 text-center">
              Archive is empty.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
