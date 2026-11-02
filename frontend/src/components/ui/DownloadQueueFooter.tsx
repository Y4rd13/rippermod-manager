import { useCallback, useMemo, useState } from "react";
import { Check, ChevronUp, Download, Loader2, PackagePlus, Trash2 } from "lucide-react";

import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { FomodWizard } from "@/components/mods/FomodWizard";
import { DownloadProgress } from "@/components/ui/DownloadProgress";
import { useCancelDownload } from "@/hooks/mutations";
import { useAvailableArchives } from "@/hooks/queries";
import { useInstallFlow } from "@/hooks/use-install-flow";
import { summarizeDownloads } from "@/lib/download-progress";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { TERMINAL_STATUSES, useDownloadStore } from "@/stores/download-store";
import { useUIStore } from "@/stores/ui-store";

export function DownloadQueueFooter() {
  const jobs = useDownloadStore((s) => s.jobs);
  const footerExpanded = useDownloadStore((s) => s.footerExpanded);
  const toggleFooter = useDownloadStore((s) => s.toggleFooter);
  const clearCompleted = useDownloadStore((s) => s.clearCompleted);
  const activeGameName = useUIStore((s) => s.activeGameName);
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed);
  const cancelDownload = useCancelDownload();
  const { data: archives = [] } = useAvailableArchives(activeGameName ?? "");
  const jobArray = useMemo(() => Object.values(jobs), [jobs]);
  const {
    handleInstallByFilename,
    fomodArchive,
    dismissFomod,
    conflicts,
    dismissConflicts,
    handleInstallWithSkip,
    handleInstallOverwrite,
  } = useInstallFlow(activeGameName ?? "", archives, jobArray);

  const [installingFiles, setInstallingFiles] = useState<Set<string>>(new Set());

  const handleInstall = useCallback(
    async (nexusModId: number, fileName: string) => {
      setInstallingFiles((prev) => new Set(prev).add(fileName));
      try {
        await handleInstallByFilename(nexusModId, fileName);
      } finally {
        setInstallingFiles((prev) => {
          const next = new Set(prev);
          next.delete(fileName);
          return next;
        });
      }
    },
    [handleInstallByFilename],
  );

  const jobList = useMemo(
    () =>
      [...jobArray].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      ),
    [jobArray],
  );

  const { terminalJobs, summary } = useMemo(
    () => ({
      terminalJobs: jobList.filter((job) => TERMINAL_STATUSES.has(job.status)),
      summary: summarizeDownloads(jobList),
    }),
    [jobList],
  );

  if (!activeGameName || jobList.length === 0) return null;

  // Only downloading jobs feed the percentage; queued ones are named instead of averaged in.
  const allDone = summary.active === 0;
  const barPercent = summary.downloadingPercent ?? (allDone ? 100 : 0);
  const countLabel = allDone
    ? `${terminalJobs.length} completed`
    : `${plural(summary.active, "download")}${summary.queued > 0 ? ` · ${summary.queued} queued` : ""}`;

  return (
    <>
    <div
      className={cn(
        "fixed bottom-0 right-0 z-30 animate-slide-up bg-surface-1 border-t border-border transition-[left] duration-200",
        sidebarCollapsed ? "left-14" : "left-52",
      )}
    >
      <button
        type="button"
        onClick={toggleFooter}
        aria-expanded={footerExpanded}
        aria-label={footerExpanded ? "Hide downloads" : "Show downloads"}
        className="flex w-full items-center gap-3 px-4 h-10 hover:bg-surface-2/50 transition-colors"
      >
        <Download size={16} className="text-accent-text shrink-0" />
        <span className="text-sm text-text-secondary whitespace-nowrap">{countLabel}</span>
        <div className="flex-1 mx-2 h-1.5 rounded-full bg-surface-3 overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-300",
              allDone ? "bg-success" : "bg-accent",
            )}
            style={{ width: `${Math.min(barPercent, 100)}%` }}
          />
        </div>
        {(summary.downloadingPercent != null || allDone) && (
          <span className="text-xs text-text-muted tabular-nums whitespace-nowrap">
            {barPercent}%
          </span>
        )}
        <ChevronUp
          size={16}
          className={cn(
            "text-text-muted shrink-0 transition-transform duration-200",
            footerExpanded && "rotate-180",
          )}
        />
      </button>

      <div
        className={cn(
          "overflow-hidden transition-all duration-200 ease-out",
          footerExpanded ? "max-h-[240px]" : "max-h-0",
        )}
      >
        <div className="border-t border-border" />
        <div className="overflow-y-auto max-h-[200px] px-4 py-2 space-y-2">
          {jobList.map((job) => {
            const isCompleted = job.status === "completed";
            const isInstalled = isCompleted && archives.some(
              (a) => a.filename === job.file_name && a.is_installed,
            );
            const isInstalling = isCompleted && installingFiles.has(job.file_name);

            return (
              <div key={job.id} className="flex items-center gap-2 animate-fade-in">
                <div className="flex-1 min-w-0">
                  <DownloadProgress
                    job={job}
                    onCancel={
                      job.status === "pending" ||
                      job.status === "queued" ||
                      job.status === "downloading"
                        ? () =>
                            cancelDownload.mutate({
                              gameName: activeGameName,
                              jobId: job.id,
                            })
                        : undefined
                    }
                  />
                </div>
                {isCompleted && (
                  isInstalled ? (
                    <span className="flex items-center gap-1 text-xs text-success shrink-0">
                      <Check size={14} />
                      Installed
                    </span>
                  ) : isInstalling ? (
                    <Loader2 size={16} className="text-accent-text shrink-0 animate-spin" />
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleInstall(job.nexus_mod_id, job.file_name)}
                      className="p-1 text-accent-text hover:text-text-primary transition-colors shrink-0"
                      title="Install mod"
                      aria-label={`Install ${job.file_name}`}
                    >
                      <PackagePlus size={16} />
                    </button>
                  )
                )}
              </div>
            );
          })}
        </div>
        {terminalJobs.length > 0 && (
          <>
            <div className="border-t border-border" />
            <div className="flex justify-end px-4 py-1.5">
              <button
                onClick={clearCompleted}
                className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors"
              >
                Clear completed
                <Trash2 size={12} />
              </button>
            </div>
          </>
        )}
      </div>
    </div>

    {fomodArchive && (
      <FomodWizard
        gameName={activeGameName!}
        archiveFilename={fomodArchive}
        onDismiss={dismissFomod}
        onInstallComplete={dismissFomod}
      />
    )}

    {conflicts && (
      <ConflictDialog
        conflicts={conflicts}
        onCancel={dismissConflicts}
        onSkip={handleInstallWithSkip}
        onOverwrite={handleInstallOverwrite}
      />
    )}
    </>
  );
}
