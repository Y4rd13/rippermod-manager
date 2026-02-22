import { useEffect } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import type { ProfileCompareOut } from "@/types/api";

interface Props {
  compare: ProfileCompareOut;
  onClose: () => void;
}

export function ProfileCompareDialog({ compare, onClose }: Props) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="compare-dialog-title"
        className="w-full max-w-2xl rounded-xl border border-border bg-surface-1 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="compare-dialog-title" className="mb-4 text-lg font-semibold text-text-primary">
          {compare.profile_a_name} vs {compare.profile_b_name}
        </h3>

        <div className="mb-4 grid grid-cols-3 gap-4">
          {/* Only in A */}
          <div>
            <div className="mb-2 flex items-center gap-2">
              <span className="text-sm font-medium text-text-secondary">
                Only in {compare.profile_a_name}
              </span>
              <Badge variant="neutral">{compare.only_in_a_count}</Badge>
            </div>
            <div className="max-h-48 overflow-y-auto rounded border border-border bg-surface-0 p-2">
              {compare.only_in_a.length === 0 ? (
                <p className="text-xs text-text-muted">None</p>
              ) : (
                compare.only_in_a.map((entry) => (
                  <div
                    key={entry.installed_mod_id ?? `a-${entry.mod_name}`}
                    className="py-0.5 text-xs text-text-primary"
                  >
                    {entry.mod_name}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Shared */}
          <div>
            <div className="mb-2 flex items-center gap-2">
              <span className="text-sm font-medium text-text-secondary">Shared</span>
              <Badge variant="neutral">{compare.in_both_count}</Badge>
            </div>
            <div className="max-h-48 overflow-y-auto rounded border border-border bg-surface-0 p-2">
              {compare.in_both.length === 0 ? (
                <p className="text-xs text-text-muted">None</p>
              ) : (
                compare.in_both.map((entry) => (
                  <div
                    key={entry.installed_mod_id ?? `both-${entry.mod_name}`}
                    className={`py-0.5 text-xs ${
                      entry.enabled_in_a !== entry.enabled_in_b
                        ? "text-warning"
                        : "text-text-primary"
                    }`}
                  >
                    {entry.mod_name}
                    {entry.enabled_in_a !== entry.enabled_in_b && (
                      <span className="ml-1 text-text-muted">
                        ({entry.enabled_in_a ? "on" : "off"} / {entry.enabled_in_b ? "on" : "off"})
                      </span>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Only in B */}
          <div>
            <div className="mb-2 flex items-center gap-2">
              <span className="text-sm font-medium text-text-secondary">
                Only in {compare.profile_b_name}
              </span>
              <Badge variant="neutral">{compare.only_in_b_count}</Badge>
            </div>
            <div className="max-h-48 overflow-y-auto rounded border border-border bg-surface-0 p-2">
              {compare.only_in_b.length === 0 ? (
                <p className="text-xs text-text-muted">None</p>
              ) : (
                compare.only_in_b.map((entry) => (
                  <div
                    key={entry.installed_mod_id ?? `b-${entry.mod_name}`}
                    className="py-0.5 text-xs text-text-primary"
                  >
                    {entry.mod_name}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
