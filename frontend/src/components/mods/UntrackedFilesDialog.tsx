import { X } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { useUntrackedFiles } from "@/hooks/use-deploy";

interface UntrackedFilesDialogProps {
  gameName: string;
  onClose: () => void;
}

export function UntrackedFilesDialog({ gameName, onClose }: UntrackedFilesDialogProps) {
  const { data, isLoading } = useUntrackedFiles(gameName);

  const files = data?.files ?? [];

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="untracked-files-dialog-title"
        className="w-full max-w-2xl rounded-xl border border-border bg-surface-1 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3
            id="untracked-files-dialog-title"
            className="text-lg font-semibold text-text-primary"
          >
            Untracked files
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-text-muted hover:text-text-primary"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        {isLoading ? (
          <p className="text-sm text-text-muted">Scanning…</p>
        ) : files.length === 0 ? (
          <p className="text-sm text-success">No untracked files in known mod roots.</p>
        ) : (
          <>
            <p className="mb-3 text-sm text-text-secondary">
              These files exist in your game's mod directories but are not owned by any
              RipperMod-installed mod. They were either added manually or remain from a previous
              tool.
            </p>
            <ul className="mb-4 max-h-64 overflow-y-auto rounded border border-border bg-surface-0 p-2 space-y-0.5">
              {files.map((p) => (
                <li key={p} className="font-mono text-xs text-text-muted">
                  {p}
                </li>
              ))}
            </ul>
          </>
        )}

        <div className="flex justify-end">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
