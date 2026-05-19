import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { useCollectionStatus, useCollectionStream } from "@/hooks/use-collections";

interface Props {
  collectionId: number;
  onFinished: () => void;
  onCancel: () => void;
}

const TERMINAL_STATUSES = ["installed", "partial", "failed", "cancelled"];

export function CollectionInstallProgress({ collectionId, onFinished, onCancel }: Props) {
  const { data: status } = useCollectionStatus(collectionId);
  const { latestEvent } = useCollectionStream(collectionId);

  const percent = latestEvent?.percent ?? status?.percent ?? 0;
  const currentMod = latestEvent?.current_mod ?? "";
  const phase = latestEvent?.phase ?? status?.status ?? "pending";
  const terminal = status ? TERMINAL_STATUSES.includes(status.status) : false;

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

        <div className="flex justify-end">
          <button
            type="button"
            onClick={terminal ? onFinished : onCancel}
            className="rounded-md border border-border bg-surface-0 px-3 py-1.5 text-sm text-text-primary hover:bg-surface-2"
          >
            {terminal ? "Close" : "Run in background"}
          </button>
        </div>
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
