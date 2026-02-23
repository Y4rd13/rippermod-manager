import { Package } from "lucide-react";

import { Button } from "@/components/ui/Button";

interface Props {
  archiveFilename: string;
  onDismiss: () => void;
}

export function FomodDialog({ archiveFilename, onDismiss }: Props) {
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="fomod-dialog-title"
        className="w-full max-w-md rounded-xl border border-border bg-surface-1 p-6"
      >
        <div className="mb-4 flex items-center gap-2 text-warning">
          <Package size={20} />
          <h3 id="fomod-dialog-title" className="text-lg font-semibold text-text-primary">
            FOMOD Installer Detected
          </h3>
        </div>
        <p className="mb-2 text-sm text-text-secondary">
          <span className="font-mono text-text-primary">{archiveFilename}</span> contains a FOMOD
          installer with multiple configuration options.
        </p>
        <p className="mb-4 text-sm text-text-muted">
          FOMOD archives require a dedicated mod manager (Vortex or MO2) to install correctly.
          Auto-install is not supported for this archive type.
        </p>
        <div className="flex justify-end">
          <Button size="sm" onClick={onDismiss}>
            Dismiss
          </Button>
        </div>
      </div>
    </div>
  );
}
