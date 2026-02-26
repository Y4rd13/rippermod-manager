import { X } from "lucide-react";

interface ConflictDetailDrawerProps {
  sourceName: string;
  targetName: string;
  sharedFiles: string[];
  onClose: () => void;
}

export function ConflictDetailDrawer({
  sourceName,
  targetName,
  sharedFiles,
  onClose,
}: ConflictDetailDrawerProps) {
  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        className="fixed right-0 top-0 bottom-0 z-50 w-[400px] max-w-[90vw] bg-surface-1 border-l border-border shadow-xl animate-slide-in-right flex flex-col"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-text-primary truncate">
              Shared Files
            </h3>
            <p className="text-xs text-text-muted truncate">
              {sourceName} &harr; {targetName}
            </p>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-lg p-1.5 text-text-muted hover:text-text-primary hover:bg-surface-2 transition-colors"
          >
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <p className="text-xs text-text-muted mb-3">
            {sharedFiles.length} conflicting file{sharedFiles.length !== 1 ? "s" : ""}
          </p>
          <ul className="space-y-1">
            {sharedFiles.map((file) => (
              <li
                key={file}
                className="text-xs font-mono text-text-secondary bg-surface-2 rounded px-2 py-1.5 break-all"
              >
                {file}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}
