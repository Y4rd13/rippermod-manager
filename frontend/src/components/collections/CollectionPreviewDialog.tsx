import { Download, Loader2, Package, RefreshCw, User, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import {
  useCollectionPreview,
  useInstallCollection,
} from "@/hooks/use-collections";
import { toast } from "@/stores/toast-store";
import type { CollectionStatus } from "@/types/api";

interface Props {
  gameName: string;
  slug: string;
  revision: number;
  forceReinstall?: boolean;
  onClose: () => void;
  onInstallStarted: (status: CollectionStatus) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function CollectionPreviewDialog({
  gameName,
  slug,
  revision,
  forceReinstall = false,
  onClose,
  onInstallStarted,
}: Props) {
  const { data, isLoading, error } = useCollectionPreview(gameName, slug, revision);
  const install = useInstallCollection(gameName);
  const [includeOptional, setIncludeOptional] = useState(true);
  const [skipModIds, setSkipModIds] = useState<Set<number>>(new Set());

  const mods = data?.mods ?? [];
  const requiredCount = useMemo(() => mods.filter((m) => !m.optional).length, [mods]);
  const optionalCount = useMemo(() => mods.filter((m) => m.optional).length, [mods]);

  const handleInstall = () => {
    install.mutate(
      {
        slug,
        revision,
        include_optional: includeOptional,
        skip_mod_ids: Array.from(skipModIds),
        force_reinstall: forceReinstall,
      },
      {
        onSuccess: (status) => {
          onInstallStarted(status);
        },
        onError: (err) => {
          toast.error(
            forceReinstall ? "Couldn't start update" : "Couldn't start install",
            err.message,
          );
        },
      },
    );
  };

  const toggleSkip = (modId: number) => {
    setSkipModIds((prev) => {
      const next = new Set(prev);
      if (next.has(modId)) next.delete(modId);
      else next.add(modId);
      return next;
    });
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-xl border border-border bg-surface-1 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-4 border-b border-border p-5">
          <div className="flex gap-3">
            {data?.tile_image_url && (
              <img
                src={data.tile_image_url}
                alt=""
                className="h-16 w-16 rounded-md object-cover"
              />
            )}
            <div>
              <h2 className="text-lg font-semibold text-text-primary">
                {data?.name || "Loading collection..."}
              </h2>
              {data && (
                <p className="mt-0.5 flex items-center gap-2 text-xs text-text-muted">
                  <User size={12} /> {data.author} - rev {data.revision_number}
                </p>
              )}
              {data?.summary && (
                <p className="mt-2 text-sm text-text-secondary">{data.summary}</p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-text-muted hover:text-text-primary"
          >
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-auto p-5">
          {isLoading && (
            <div className="flex items-center justify-center gap-2 py-12 text-text-muted">
              <Loader2 className="animate-spin" size={16} /> Resolving collection from Nexus...
            </div>
          )}
          {error && (
            <div className="rounded-md border border-danger/30 bg-danger/10 p-4 text-sm text-danger">
              Couldn't load collection: {error.message}
            </div>
          )}
          {data && (
            <>
              <div className="mb-4 flex items-center gap-4 text-xs text-text-muted">
                <span className="flex items-center gap-1">
                  <Package size={12} /> {requiredCount} required
                </span>
                {optionalCount > 0 && (
                  <span className="flex items-center gap-1">
                    <Package size={12} /> {optionalCount} optional
                  </span>
                )}
                <span className="flex items-center gap-1">
                  <Download size={12} /> {formatBytes(data.total_size_bytes)} total
                </span>
              </div>

              {optionalCount > 0 && (
                <label className="mb-3 flex items-center gap-2 text-sm text-text-secondary">
                  <input
                    type="checkbox"
                    checked={includeOptional}
                    onChange={(e) => setIncludeOptional(e.target.checked)}
                    className="h-4 w-4"
                  />
                  Install optional mods
                </label>
              )}

              <ul className="space-y-1.5">
                {mods.map((mod) => {
                  const skipped = skipModIds.has(mod.nexus_mod_id);
                  const dimmed = skipped || (!includeOptional && mod.optional);
                  // Composite key — a collection MAY include two files from
                  // the same mod (e.g. main + patch), so ``nexus_mod_id``
                  // alone is not unique. ``nexus_file_id`` disambiguates.
                  return (
                    <li
                      key={`${mod.nexus_mod_id}-${mod.nexus_file_id}`}
                      className={`flex items-center justify-between gap-3 rounded-md border border-border bg-surface-0 p-2 ${dimmed ? "opacity-50" : ""}`}
                    >
                      <div className="flex min-w-0 items-center gap-2">
                        {mod.picture_url && (
                          <img
                            src={mod.picture_url}
                            alt=""
                            className="h-8 w-8 shrink-0 rounded object-cover"
                          />
                        )}
                        <div className="min-w-0">
                          <p className="truncate text-sm text-text-primary">{mod.name}</p>
                          <p className="truncate text-xs text-text-muted">
                            by {mod.author} - v{mod.version} - {formatBytes(mod.size_bytes)}
                            {mod.optional && " - optional"}
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => toggleSkip(mod.nexus_mod_id)}
                        className="text-xs text-text-muted hover:text-text-primary"
                      >
                        {skipped ? "Include" : "Skip"}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>

        <footer className="flex justify-end gap-2 border-t border-border p-4">
          <Button variant="secondary" size="sm" onClick={onClose} disabled={install.isPending}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleInstall}
            loading={install.isPending}
            disabled={!data || isLoading}
          >
            {forceReinstall ? (
              <>
                <RefreshCw size={14} /> Update to rev {revision}
              </>
            ) : (
              <>
                <Download size={14} /> Install collection
              </>
            )}
          </Button>
        </footer>
      </div>
    </div>
  );
}
