import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import type { ProfileDiffOut } from "@/types/api";

interface Props {
  diff: ProfileDiffOut;
  loading?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

const ACTION_STYLES: Record<string, string> = {
  enable: "text-success",
  disable: "text-warning",
  missing: "text-danger",
  unchanged: "text-text-muted",
};

const ACTION_LABELS: Record<string, string> = {
  enable: "Enable",
  disable: "Disable",
  missing: "Missing",
  unchanged: "No change",
};

export function ProfileDiffDialog({ diff, loading, onCancel, onConfirm }: Props) {
  const [showUnchanged, setShowUnchanged] = useState(false);

  const grouped = {
    enable: diff.entries.filter((e) => e.action === "enable"),
    disable: diff.entries.filter((e) => e.action === "disable"),
    missing: diff.entries.filter((e) => e.action === "missing"),
    unchanged: diff.entries.filter((e) => e.action === "unchanged"),
  };

  const hasChanges =
    diff.enable_count > 0 || diff.disable_count > 0 || diff.missing_count > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="diff-dialog-title"
        className="w-full max-w-lg rounded-xl border border-border bg-surface-1 p-6"
      >
        <h3 id="diff-dialog-title" className="mb-4 text-lg font-semibold text-text-primary">
          Load Profile: {diff.profile_name}
        </h3>

        <div className="mb-4 flex flex-wrap gap-2">
          {diff.enable_count > 0 && (
            <Badge variant="success">{diff.enable_count} to enable</Badge>
          )}
          {diff.disable_count > 0 && (
            <Badge variant="warning">{diff.disable_count} to disable</Badge>
          )}
          {diff.missing_count > 0 && (
            <Badge variant="danger">{diff.missing_count} missing</Badge>
          )}
          {diff.unchanged_count > 0 && (
            <Badge variant="neutral">{diff.unchanged_count} unchanged</Badge>
          )}
        </div>

        <div className="mb-4 max-h-64 overflow-y-auto rounded border border-border bg-surface-0 p-3">
          {!hasChanges && diff.unchanged_count === 0 && (
            <p className="text-sm text-text-muted">No mods in this profile.</p>
          )}

          {(["enable", "disable", "missing"] as const).map((action) =>
            grouped[action].map((entry) => (
              <div key={`${action}-${entry.installed_mod_id}`} className="py-1 text-sm">
                <span className={ACTION_STYLES[action]}>[{ACTION_LABELS[action]}]</span>{" "}
                <span className="text-text-primary">{entry.mod_name}</span>
              </div>
            )),
          )}

          {grouped.unchanged.length > 0 && (
            <div className="mt-2 border-t border-border pt-2">
              <button
                type="button"
                className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary"
                onClick={() => setShowUnchanged(!showUnchanged)}
              >
                {showUnchanged ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                {grouped.unchanged.length} unchanged mod
                {grouped.unchanged.length !== 1 && "s"}
              </button>
              {showUnchanged &&
                grouped.unchanged.map((entry) => (
                  <div
                    key={`unchanged-${entry.installed_mod_id}`}
                    className="py-0.5 pl-4 text-sm text-text-muted"
                  >
                    {entry.mod_name}
                  </div>
                ))}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button size="sm" loading={loading} onClick={onConfirm}>
            Confirm Load
          </Button>
        </div>
      </div>
    </div>
  );
}
