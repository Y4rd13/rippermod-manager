import { Archive, X } from "lucide-react";
import { useEffect } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import type { InstalledModOut } from "@/types/api";

interface Props {
  modName: string;
  entries: InstalledModOut[];
  actionLabel: string;
  actionVariant?: "primary" | "secondary" | "danger";
  onSelect: (modId: number) => void;
  onSelectAll: () => void;
  onCancel: () => void;
}

export function InstalledFileSelector({
  modName,
  entries,
  actionLabel,
  actionVariant = "primary",
  onSelect,
  onSelectAll,
  onCancel,
}: Props) {
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
        className="w-full max-w-lg rounded-xl border border-border bg-surface-1 p-6 animate-modal-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary truncate pr-4">
            {actionLabel}: {modName}
          </h3>
          <button
            onClick={onCancel}
            className="shrink-0 rounded-md p-1 text-text-muted hover:bg-surface-3 hover:text-text-primary"
          >
            <X size={16} />
          </button>
        </div>

        <p className="mb-3 text-xs text-text-secondary">
          This mod has {entries.length} installed files. Select which one to{" "}
          {actionLabel.toLowerCase()}.
        </p>

        <div className="space-y-2 max-h-[50vh] overflow-y-auto">
          {entries.map((entry) => (
            <button
              key={entry.id}
              type="button"
              onClick={() => onSelect(entry.id)}
              className="w-full text-left rounded-lg border border-border bg-surface-0 p-3 hover:bg-surface-2 hover:border-accent transition-colors"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-text-primary truncate">
                  {entry.name}
                </span>
                <Badge variant={entry.disabled ? "danger" : "success"}>
                  {entry.disabled ? "Disabled" : "Enabled"}
                </Badge>
              </div>
              {entry.source_archive && (
                <div className="mt-1 flex items-center gap-1 text-xs text-text-muted">
                  <Archive size={10} className="shrink-0" />
                  <span className="truncate">{entry.source_archive}</span>
                </div>
              )}
              <div className="mt-1 text-xs text-text-muted">
                v{entry.installed_version || "?"} &middot; {entry.file_count} file
                {entry.file_count !== 1 ? "s" : ""}
              </div>
            </button>
          ))}
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant={actionVariant} size="sm" onClick={onSelectAll}>
            {actionLabel} All ({entries.length})
          </Button>
        </div>
      </div>
    </div>
  );
}
