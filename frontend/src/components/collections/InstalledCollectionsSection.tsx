import { Package, RefreshCw, Trash2, User } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import {
  useCheckCollectionUpdates,
  useCollectionList,
  useUninstallCollection,
} from "@/hooks/use-collections";
import { useCollectionInstallStore } from "@/stores/collection-install-store";
import { toast } from "@/stores/toast-store";
import type { CollectionStatus } from "@/types/api";

interface Props {
  gameName: string;
}

function statusBadgeClass(status: CollectionStatus["status"]): string {
  switch (status) {
    case "installed":
      return "bg-success/15 text-success";
    case "partial":
      return "bg-warning/15 text-warning";
    case "failed":
    case "cancelled":
      return "bg-danger/15 text-danger";
    case "awaiting_nxm":
      return "bg-warning/15 text-warning";
    case "downloading":
    case "installing":
    case "pending":
      return "bg-accent/15 text-accent";
  }
}

function statusLabel(status: CollectionStatus["status"]): string {
  if (status === "awaiting_nxm") return "Awaiting NXM";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function hasUpdate(coll: CollectionStatus): boolean {
  return (
    coll.latest_known_revision_number != null &&
    coll.latest_known_revision_number > coll.revision_number
  );
}

/**
 * Renders the user's installed Nexus Collections as a header above the
 * regular installed-mods table. Each row supports uninstall-the-whole-
 * collection (cascade through child mods + final deploy) and -- once the
 * user has run "Check for updates" -- a per-row Update button when a
 * newer revision is published.
 *
 * Hidden when the user has no installed collections (no empty state — the
 * collections concept is only relevant once one has been installed).
 */
export function InstalledCollectionsSection({ gameName }: Props) {
  const { data: collections } = useCollectionList(gameName);
  const uninstall = useUninstallCollection(gameName);
  const checkUpdates = useCheckCollectionUpdates(gameName);
  const openInstall = useCollectionInstallStore((s) => s.open);
  const [confirmTarget, setConfirmTarget] = useState<CollectionStatus | null>(null);

  if (!collections || collections.length === 0) return null;

  const handleConfirm = () => {
    if (!confirmTarget) return;
    const target = confirmTarget;
    uninstall.mutate(target.id, {
      onSuccess: (result) => {
        toast.success(
          `Removed collection "${target.name}"`,
          `Uninstalled ${result.removed_mods} mod${result.removed_mods === 1 ? "" : "s"}` +
            (result.failed_mods > 0 ? ` (${result.failed_mods} failed)` : ""),
        );
        setConfirmTarget(null);
      },
      onError: (err) => {
        toast.error(`Couldn't remove "${target.name}"`, err.message);
        setConfirmTarget(null);
      },
    });
  };

  const handleCheckUpdates = () => {
    checkUpdates.mutate(undefined, {
      onSuccess: (result) => {
        const withUpdates = result.filter((r) => r.has_update).length;
        const withErrors = result.filter((r) => r.error).length;
        if (withErrors > 0) {
          toast.warning(
            "Update check finished",
            `${withUpdates} update${withUpdates === 1 ? "" : "s"} found, ${withErrors} failed`,
          );
        } else if (withUpdates > 0) {
          toast.success(
            "Updates available",
            `${withUpdates} collection${withUpdates === 1 ? "" : "s"} ` +
              `${withUpdates === 1 ? "has" : "have"} a newer revision on Nexus`,
          );
        } else {
          toast.info("Up to date", "No new revisions on Nexus");
        }
      },
      onError: (err) => {
        toast.error("Couldn't check for updates", err.message);
      },
    });
  };

  const handleUpdate = (coll: CollectionStatus) => {
    if (!coll.latest_known_revision_number) return;
    openInstall({
      gameName,
      slug: coll.slug,
      revision: coll.latest_known_revision_number,
      forceReinstall: true,
    });
  };

  return (
    <>
      <div className="mb-4 rounded-lg border border-border bg-surface-1 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 text-sm font-medium text-text-primary">
            <Package size={14} /> Installed collections ({collections.length})
          </h3>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleCheckUpdates}
            loading={checkUpdates.isPending}
            title="Ask Nexus if any installed collection has a newer revision"
          >
            <RefreshCw size={12} /> Check for updates
          </Button>
        </div>
        <ul className="space-y-1.5">
          {collections.map((coll) => {
            const updateAvailable = hasUpdate(coll);
            return (
              <li
                key={coll.id}
                className="flex items-center justify-between gap-3 rounded-md border border-border bg-surface-0 p-2.5"
              >
                <div className="flex min-w-0 items-center gap-3">
                  {coll.tile_image_url && (
                    <img
                      src={coll.tile_image_url}
                      alt=""
                      className="h-10 w-10 shrink-0 rounded object-cover"
                    />
                  )}
                  <div className="min-w-0">
                    <p className="truncate text-sm text-text-primary">{coll.name}</p>
                    <p className="flex items-center gap-2 truncate text-xs text-text-muted">
                      <User size={11} /> {coll.author} - rev {coll.revision_number} -{" "}
                      {coll.completed_mods}/{coll.total_mods} mods
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {updateAvailable && (
                    <span className="rounded bg-accent/15 px-1.5 py-0.5 text-xs text-accent">
                      Update to rev {coll.latest_known_revision_number}
                    </span>
                  )}
                  <span
                    className={`rounded px-1.5 py-0.5 text-xs ${statusBadgeClass(coll.status)}`}
                  >
                    {statusLabel(coll.status)}
                  </span>
                  {updateAvailable && (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => handleUpdate(coll)}
                      title={`Re-install at revision ${coll.latest_known_revision_number}`}
                    >
                      <RefreshCw size={12} /> Update
                    </Button>
                  )}
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setConfirmTarget(coll)}
                    title="Uninstall this collection and all its mods"
                  >
                    <Trash2 size={12} /> Uninstall
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      {confirmTarget && (
        <ConfirmDialog
          title="Uninstall collection?"
          message={
            `"${confirmTarget.name}" will be removed along with all ${confirmTarget.total_mods} mods that were installed as part of it. ` +
            `Your downloaded archives in downloaded_mods/ are not touched, so you can re-install later by clicking the collection link again. Close Cyberpunk 2077 first.`
          }
          confirmLabel="Uninstall collection"
          variant="warning"
          icon={Trash2}
          loading={uninstall.isPending}
          onConfirm={handleConfirm}
          onCancel={() => setConfirmTarget(null)}
        />
      )}
    </>
  );
}
