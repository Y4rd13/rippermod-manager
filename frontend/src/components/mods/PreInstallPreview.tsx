import {
  Check,
  ChevronDown,
  ChevronRight,
  File,
  Folder,
  FolderOpen,
  Loader2,
  Pencil,
  X,
} from "lucide-react";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { useArchivePreview } from "@/hooks/queries";
import { buildFileTree } from "@/lib/file-tree";
import { formatBytes } from "@/lib/format";
import type { ArchiveEntryNode } from "@/types/api";

interface Props {
  gameName: string;
  archiveFilename: string;
  onConfirm: (fileRenames: Record<string, string>) => void;
  onCancel: () => void;
}

const PreviewTreeNode = memo(function PreviewTreeNode({
  node,
  depth,
  parentPath,
  renames,
  onRename,
}: {
  node: ArchiveEntryNode;
  depth: number;
  parentPath: string;
  renames: Record<string, string>;
  onRename: (original: string, newPath: string | null) => void;
}) {
  const [open, setOpen] = useState(true);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const fullPath = parentPath ? `${parentPath}/${node.name}` : node.name;

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

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
            <PreviewTreeNode
              key={child.name}
              node={child}
              depth={depth + 1}
              parentPath={fullPath}
              renames={renames}
              onRename={onRename}
            />
          ))}
      </div>
    );
  }

  const renamedPath = renames[fullPath];
  const isRenamed = renamedPath != null;
  const displayName = isRenamed ? renamedPath.split("/").pop() ?? renamedPath : node.name;

  const startEditing = () => {
    setDraft(renamedPath ?? fullPath);
    setEditing(true);
  };

  const commitEdit = () => {
    setEditing(false);
    const trimmed = draft.trim();
    if (!trimmed || trimmed === fullPath) {
      onRename(fullPath, null);
    } else if (trimmed.includes("..") || trimmed.startsWith("/")) {
      onRename(fullPath, null);
    } else {
      onRename(fullPath, trimmed);
    }
  };

  const cancelEdit = () => setEditing(false);

  if (editing) {
    return (
      <div
        className="flex items-center gap-1.5 py-0.5 pr-2"
        style={{ paddingLeft: `${depth * 1.25}rem` }}
      >
        <File size={14} className="shrink-0 text-text-muted" />
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitEdit();
            if (e.key === "Escape") cancelEdit();
          }}
          onBlur={commitEdit}
          className="min-w-0 flex-1 rounded border border-accent bg-surface-0 px-2 py-0.5 font-mono text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
        />
      </div>
    );
  }

  return (
    <div
      className="group flex items-center gap-1.5 py-0.5 hover:bg-surface-2/50 rounded pr-2"
      style={{ paddingLeft: `${depth * 1.25}rem` }}
    >
      <File size={14} className="shrink-0 text-text-muted" />
      <span
        className={`font-mono text-xs truncate ${isRenamed ? "text-accent font-medium" : "text-text-secondary"}`}
        title={isRenamed ? renamedPath : fullPath}
      >
        {displayName}
      </span>
      {isRenamed && (
        <span className="shrink-0 text-[10px] text-accent bg-accent/10 px-1 rounded">
          renamed
        </span>
      )}
      <span className="ml-auto shrink-0 font-mono text-xs text-text-muted whitespace-nowrap">
        {formatBytes(node.size)}
      </span>
      <button
        onClick={(e) => { e.stopPropagation(); startEditing(); }}
        title="Rename file"
        className="shrink-0 rounded p-0.5 text-text-muted opacity-0 group-hover:opacity-100 hover:text-accent hover:bg-accent/10 transition-all"
      >
        <Pencil size={12} />
      </button>
      {isRenamed && (
        <button
          onClick={(e) => { e.stopPropagation(); onRename(fullPath, null); }}
          title="Revert rename"
          className="shrink-0 rounded p-0.5 text-text-muted opacity-0 group-hover:opacity-100 hover:text-warning hover:bg-warning/10 transition-all"
        >
          <X size={12} />
        </button>
      )}
    </div>
  );
});

export function PreInstallPreview({ gameName, archiveFilename, onConfirm, onCancel }: Props) {
  const { data: preview, isLoading, error } = useArchivePreview(gameName, archiveFilename);
  const [renames, setRenames] = useState<Record<string, string>>({});

  const tree = useMemo(() => {
    if (!preview) return [];
    const files = preview.files
      .filter((f) => !f.is_dir)
      .map((f) => ({ file_path: f.file_path, file_size: f.size }));
    return buildFileTree(files);
  }, [preview]);

  const handleRename = useCallback((original: string, newPath: string | null) => {
    setRenames((prev) => {
      const next = { ...prev };
      if (newPath == null) {
        delete next[original];
      } else {
        next[original] = newPath;
      }
      return next;
    });
  }, []);

  const renameCount = Object.keys(renames).length;

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onCancel]);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="preview-dialog-title"
        className="w-full max-w-2xl rounded-xl border border-border bg-surface-1 p-6 animate-modal-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 id="preview-dialog-title" className="text-sm font-semibold text-text-primary truncate pr-4">
            Install with Options
          </h3>
          <button
            onClick={onCancel}
            className="shrink-0 rounded-md p-1 text-text-muted hover:bg-surface-3 hover:text-text-primary"
          >
            <X size={16} />
          </button>
        </div>

        <p className="mb-1 text-xs text-text-muted truncate" title={archiveFilename}>
          {archiveFilename}
        </p>

        {isLoading && (
          <div className="flex items-center justify-center py-12 text-text-muted">
            <Loader2 size={20} className="animate-spin mr-2" />
            Loading archive contents...
          </div>
        )}

        {error && (
          <div className="py-8 text-center text-sm text-danger">
            Failed to load archive contents.
          </div>
        )}

        {preview && (preview.is_fomod ? (
          <>
            <div className="py-8 text-center text-sm text-warning">
              This archive is a FOMOD installer. Use the FOMOD wizard instead.
            </div>
            <div className="mt-4 flex justify-end">
              <Button variant="secondary" size="sm" onClick={onCancel}>
                Close
              </Button>
            </div>
          </>
        ) : (
          <>
            <p className="mb-3 text-xs text-text-secondary">
              {preview.total_files} file{preview.total_files !== 1 ? "s" : ""} will be extracted.
              Click the <Pencil size={10} className="inline mx-0.5" /> icon to rename a file before install.
            </p>

            <div className="max-h-80 overflow-y-auto rounded border border-border bg-surface-0 p-1">
              {tree.map((node) => (
                <PreviewTreeNode
                  key={node.name}
                  node={node}
                  depth={0}
                  parentPath=""
                  renames={renames}
                  onRename={handleRename}
                />
              ))}
            </div>

            {renameCount > 0 && (
              <p className="mt-2 text-xs text-accent">
                {renameCount} file{renameCount !== 1 ? "s" : ""} will be renamed.
              </p>
            )}

            <div className="mt-4 flex justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={onCancel}>
                Cancel
              </Button>
              <Button size="sm" onClick={() => onConfirm(renames)}>
                <Check size={14} className="mr-1" />
                Install{renameCount > 0 ? ` (${renameCount} renamed)` : ""}
              </Button>
            </div>
          </>
        ))}
      </div>
    </div>
  );
}
