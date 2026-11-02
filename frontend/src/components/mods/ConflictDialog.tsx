import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  File,
  Folder,
  FolderOpen,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { buildFileTree } from "@/lib/file-tree";
import type { ArchiveEntryNode, ConflictCheckResult } from "@/types/api";

interface Props {
  conflicts: ConflictCheckResult;
  onCancel: () => void;
  onSkip: () => void;
  onOverwrite: () => void;
}

function ConflictTreeNode({
  node,
  depth,
  parentPath,
  ownerMap,
}: {
  node: ArchiveEntryNode;
  depth: number;
  parentPath: string;
  ownerMap: Map<string, string>;
}) {
  const [open, setOpen] = useState(true);

  const fullPath = parentPath ? `${parentPath}/${node.name}` : node.name;

  if (node.is_dir) {
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
            <FolderOpen size={14} className="shrink-0 text-accent-text" />
          ) : (
            <Folder size={14} className="shrink-0 text-accent-text" />
          )}
          <span className="font-mono text-xs text-text-primary truncate">
            {node.name}
          </span>
        </button>
        {open &&
          node.children.map((child) => (
            <ConflictTreeNode
              key={child.name}
              node={child}
              depth={depth + 1}
              parentPath={fullPath}
              ownerMap={ownerMap}
            />
          ))}
      </div>
    );
  }

  const owner = ownerMap.get(fullPath);

  return (
    <div
      className="flex items-center gap-1.5 py-0.5 hover:bg-surface-2/50 rounded pr-2"
      style={{ paddingLeft: `${depth * 1.25}rem` }}
    >
      <File size={14} className="shrink-0 text-text-muted" />
      <span className="font-mono text-xs text-text-primary truncate" title={fullPath}>
        {node.name}
      </span>
      {owner && (
        <span className="ml-auto shrink-0 text-[11px] text-text-muted whitespace-nowrap">
          owned by {owner}
        </span>
      )}
    </div>
  );
}

export function ConflictDialog({ conflicts, onCancel, onSkip, onOverwrite }: Props) {
  const ownerMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const c of conflicts.conflicts) {
      map.set(c.file_path, c.owning_mod_name);
    }
    return map;
  }, [conflicts]);

  const tree = useMemo(() => {
    const files = conflicts.conflicts.map((c) => ({
      file_path: c.file_path,
      file_size: 0,
    }));
    return buildFileTree(files);
  }, [conflicts]);

  return (
    <Dialog
      onClose={onCancel}
      titleId="conflict-dialog-title"
      closeOnBackdrop={false}
      backdropClassName="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      className="w-full max-w-2xl rounded-xl border border-border bg-surface-1 p-6"
    >
      <div className="mb-4 flex items-center gap-2 text-warning">
        <AlertTriangle size={20} />
        <h3 id="conflict-dialog-title" className="text-lg font-semibold text-text-primary">
          File Conflicts Detected
        </h3>
      </div>
      <p className="mb-3 text-sm text-text-secondary">
        {conflicts.conflicts.length} file(s) conflict with installed mods:
      </p>
      <div className="mb-4 max-h-48 overflow-y-auto rounded border border-border bg-surface-0 p-2">
        {tree.map((node) => (
          <ConflictTreeNode
            key={node.name}
            node={node}
            depth={0}
            parentPath=""
            ownerMap={ownerMap}
          />
        ))}
      </div>
      <p className="mb-4 text-xs text-text-secondary">
        Install: this mod&apos;s copy is linked in the game folder. The other mod keeps its own copy
        and gets the path back if you uninstall this one. Install without these files: the listed
        files are not extracted from this mod.
      </p>
      <div className="flex justify-end gap-2">
        <Button variant="secondary" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button variant="secondary" size="sm" onClick={onSkip}>
          Install without these files
        </Button>
        <Button size="sm" onClick={onOverwrite}>
          Install
        </Button>
      </div>
    </Dialog>
  );
}
