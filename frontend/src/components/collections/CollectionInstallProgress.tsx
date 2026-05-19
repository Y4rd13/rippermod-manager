import { CheckCircle2, ExternalLink, Loader2, SkipForward, X, XCircle } from "lucide-react";
import { openUrl } from "@tauri-apps/plugin-opener";

import {
  useCancelCollectionInstall,
  useCollectionStatus,
  useCollectionStream,
  useSkipPendingNxm,
} from "@/hooks/use-collections";
import { toast } from "@/stores/toast-store";

interface Props {
  collectionId: number;
  onFinished: () => void;
  onCancel: () => void;
}

const TERMINAL_STATUSES = ["installed", "partial", "failed", "cancelled"];

export function CollectionInstallProgress({ collectionId, onFinished, onCancel }: Props) {
  const { data: status } = useCollectionStatus(collectionId);
  const { latestEvent } = useCollectionStream(collectionId);
  const skipNxm = useSkipPendingNxm(collectionId);
  const cancelInstall = useCancelCollectionInstall(collectionId);

  const percent = latestEvent?.percent ?? status?.percent ?? 0;
  const currentMod = latestEvent?.current_mod ?? "";
  const phase = latestEvent?.phase ?? status?.status ?? "pending";
  const terminal = status ? TERMINAL_STATUSES.includes(status.status) : false;
  const awaitingNxm = phase === "awaiting_nxm";
  const modPageUrl = latestEvent?.mod_page_url ?? "";
  const waitingModId = latestEvent?.mod_id ?? null;
  const waitingFileId = latestEvent?.file_id ?? null;

  const handleOpenModPage = () => {
    if (!modPageUrl) return;
    void openUrl(modPageUrl).catch(() => {
      toast.error("Couldn't open the mod page", modPageUrl);
    });
  };

  const handleSkip = () => {
    if (waitingModId == null || waitingFileId == null) return;
    skipNxm.mutate(
      { nexusModId: waitingModId, nexusFileId: waitingFileId },
      {
        onError: () => toast.error("Couldn't skip this mod, try again"),
      },
    );
  };

  const handleCancelInstall = () => {
    cancelInstall.mutate(undefined, {
      onError: () => toast.error("Couldn't cancel the install, try again"),
    });
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onClick={terminal ? onFinished : undefined}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-md rounded-xl border border-border bg-surface-1 p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center gap-2 text-text-primary">
          {terminal ? (
            status?.status === "installed" ? (
              <CheckCircle2 className="text-success" size={20} />
            ) : status?.status === "failed" ? (
              <XCircle className="text-danger" size={20} />
            ) : (
              <CheckCircle2 className="text-warning" size={20} />
            )
          ) : (
            <Loader2 className="animate-spin" size={20} />
          )}
          <h3 className="text-lg font-semibold">
            {status?.name || "Installing collection"}
          </h3>
        </div>

        <p className="mb-3 text-sm text-text-secondary">
          {terminal ? statusLabel(status?.status) : phaseLabel(phase, currentMod)}
        </p>

        {awaitingNxm && (
          <p className="mb-3 rounded-md border border-warning/30 bg-warning/10 p-3 text-xs text-warning">
            Free Nexus accounts can&apos;t auto-download. Click <strong>Open mod page</strong>{" "}
            then <strong>Mod Manager Download</strong> on Nexus to continue. The install
            resumes automatically once you do.
          </p>
        )}

        <div className="mb-3 h-2 overflow-hidden rounded-full bg-surface-0">
          <div
            className={`h-full transition-[width] ${
              status?.status === "failed"
                ? "bg-danger"
                : status?.status === "partial"
                  ? "bg-warning"
                  : "bg-accent"
            }`}
            style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
          />
        </div>

        <div className="mb-5 grid grid-cols-3 gap-2 text-center text-xs">
          <Stat label="Done" value={status?.completed_mods ?? 0} tone="success" />
          <Stat label="Skipped" value={status?.skipped_mods ?? 0} tone="warning" />
          <Stat label="Failed" value={status?.failed_mods ?? 0} tone="danger" />
        </div>

        {status?.error && (
          <p className="mb-4 rounded-md border border-danger/30 bg-danger/10 p-3 text-xs text-danger">
            {status.error}
          </p>
        )}

        {awaitingNxm ? (
          <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={handleCancelInstall}
              disabled={cancelInstall.isPending}
              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-border bg-surface-0 px-3 py-1.5 text-sm text-text-primary hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <X size={14} /> Cancel install
            </button>
            <button
              type="button"
              onClick={handleSkip}
              disabled={
                skipNxm.isPending || waitingModId == null || waitingFileId == null
              }
              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-border bg-surface-0 px-3 py-1.5 text-sm text-text-primary hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <SkipForward size={14} /> Skip mod
            </button>
            <button
              type="button"
              onClick={handleOpenModPage}
              disabled={!modPageUrl}
              className="inline-flex items-center justify-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <ExternalLink size={14} /> Open mod page
            </button>
          </div>
        ) : (
          <div className="flex justify-end">
            <button
              type="button"
              onClick={terminal ? onFinished : onCancel}
              className="rounded-md border border-border bg-surface-0 px-3 py-1.5 text-sm text-text-primary hover:bg-surface-2"
            >
              {terminal ? "Close" : "Run in background"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "success" | "warning" | "danger";
}) {
  const color =
    tone === "success" ? "text-success" : tone === "warning" ? "text-warning" : "text-danger";
  return (
    <div className="rounded-md border border-border bg-surface-0 p-2">
      <div className={`text-base font-semibold ${color}`}>{value}</div>
      <div className="text-text-muted">{label}</div>
    </div>
  );
}

function phaseLabel(phase: string, currentMod: string): string {
  switch (phase) {
    case "download":
      return currentMod ? `Downloading ${currentMod}` : "Downloading mods";
    case "awaiting_nxm":
      return currentMod
        ? `Waiting for you to start the download for ${currentMod}`
        : "Waiting for the next NXM download";
    case "install":
      return currentMod ? `Installing ${currentMod}` : "Installing mods";
    case "deploy":
      return "Linking files into the game folder";
    case "done":
      return "Install finished";
    case "error":
      return "Install crashed";
    default:
      return "Working...";
  }
}

function statusLabel(status: string | undefined): string {
  switch (status) {
    case "installed":
      return "All mods installed successfully.";
    case "partial":
      return "Install finished with some mods skipped or failed.";
    case "failed":
      return "Install failed before completing.";
    case "cancelled":
      return "Install cancelled.";
    default:
      return "Install finished.";
  }
}
