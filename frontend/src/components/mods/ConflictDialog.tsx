import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/Button";
import type { ConflictCheckResult } from "@/types/api";

interface Props {
  conflicts: ConflictCheckResult;
  onCancel: () => void;
  onSkip: () => void;
  onOverwrite: () => void;
}

export function ConflictDialog({ conflicts, onCancel, onSkip, onOverwrite }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-xl border border-border bg-surface-1 p-6">
        <div className="mb-4 flex items-center gap-2 text-warning">
          <AlertTriangle size={20} />
          <h3 className="text-lg font-semibold text-text-primary">
            File Conflicts Detected
          </h3>
        </div>
        <p className="mb-3 text-sm text-text-secondary">
          {conflicts.conflicts.length} file(s) conflict with installed mods:
        </p>
        <div className="mb-4 max-h-48 overflow-y-auto rounded border border-border bg-surface-0 p-3">
          {conflicts.conflicts.map((c) => (
            <div key={c.file_path} className="py-1 text-xs">
              <span className="font-mono text-text-primary">{c.file_path}</span>
              <span className="ml-2 text-text-muted">(owned by {c.owning_mod_name})</span>
            </div>
          ))}
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="secondary" size="sm" onClick={onSkip}>
            Skip Conflicts
          </Button>
          <Button size="sm" onClick={onOverwrite}>
            Overwrite
          </Button>
        </div>
      </div>
    </div>
  );
}
