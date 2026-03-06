import { ArrowDownToLine, Download, RotateCcw, Sparkles, X } from "lucide-react";

import { useAppUpdater } from "@/hooks/use-app-updater";
import { cn } from "@/lib/utils";
import { useUpdaterStore } from "@/stores/updater-store";

export function UpdateBanner() {
  const { status, updateInfo, downloadProgress, downloadAndInstall, restartApp } = useAppUpdater();
  const bannerDismissed = useUpdaterStore((s) => s.bannerDismissed);
  const dismissBanner = useUpdaterStore((s) => s.dismissBanner);

  const showBanner =
    !bannerDismissed &&
    (status === "available" || status === "downloading" || status === "ready") &&
    updateInfo;

  if (!showBanner) return null;

  return (
    <div className="animate-slide-down border-b border-accent/20 bg-gradient-to-r from-accent/10 via-accent/5 to-transparent px-4 py-2">
      <div className="flex items-center gap-3">
        {/* Icon */}
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/15">
          {status === "downloading" ? (
            <Download size={14} className="text-accent animate-pulse" />
          ) : status === "ready" ? (
            <RotateCcw size={14} className="text-success" />
          ) : (
            <Sparkles size={14} className="text-accent" />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {status === "available" && (
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-text-primary">
                v{updateInfo.version} available
              </span>
              {updateInfo.body && (
                <span className="text-xs text-text-muted truncate hidden sm:inline">
                  {updateInfo.body.split("\n")[0]}
                </span>
              )}
            </div>
          )}

          {status === "downloading" && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-text-secondary shrink-0">Downloading update...</span>
              <div className="flex-1 h-1.5 rounded-full bg-surface-3 overflow-hidden max-w-xs">
                <div
                  className="h-full rounded-full bg-accent transition-all duration-300"
                  style={{ width: `${downloadProgress ?? 0}%` }}
                />
              </div>
              <span className="text-xs text-text-muted tabular-nums shrink-0">
                {downloadProgress ?? 0}%
              </span>
            </div>
          )}

          {status === "ready" && (
            <span className="text-sm font-medium text-success">
              Update installed — restart to apply
            </span>
          )}
        </div>

        {/* Action button */}
        {status === "available" && (
          <button
            onClick={() => void downloadAndInstall()}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors",
              "bg-accent text-white hover:bg-accent-hover",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
            )}
          >
            <ArrowDownToLine size={12} />
            Download & Install
          </button>
        )}

        {status === "ready" && (
          <button
            onClick={() => void restartApp()}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors",
              "bg-success/15 text-success hover:bg-success/25",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success",
            )}
          >
            <RotateCcw size={12} />
            Restart Now
          </button>
        )}

        {/* Dismiss */}
        {status === "available" && (
          <button
            onClick={dismissBanner}
            aria-label="Dismiss update banner"
            className="rounded-md p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary transition-colors"
          >
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
