import { useMemo } from "react";
import { ChevronUp, Download, Trash2 } from "lucide-react";

import { DownloadProgress } from "@/components/ui/DownloadProgress";
import { useCancelDownload } from "@/hooks/mutations";
import { cn } from "@/lib/utils";
import { TERMINAL_STATUSES, useDownloadStore } from "@/stores/download-store";
import { useUIStore } from "@/stores/ui-store";
import type { DownloadJobOut } from "@/types/api";

export function DownloadQueueFooter() {
  const jobs = useDownloadStore((s) => s.jobs);
  const footerExpanded = useDownloadStore((s) => s.footerExpanded);
  const toggleFooter = useDownloadStore((s) => s.toggleFooter);
  const clearCompleted = useDownloadStore((s) => s.clearCompleted);
  const activeGameName = useUIStore((s) => s.activeGameName);
  const cancelDownload = useCancelDownload();

  const jobList = useMemo(
    () =>
      Object.values(jobs).sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      ),
    [jobs],
  );

  const { activeJobs, terminalJobs, aggregatePercent } = useMemo(() => {
    const active: DownloadJobOut[] = [];
    const terminal: DownloadJobOut[] = [];

    for (const job of jobList) {
      if (TERMINAL_STATUSES.has(job.status)) {
        terminal.push(job);
      } else {
        active.push(job);
      }
    }

    const avg = active.length > 0
      ? Math.round(active.reduce((sum, j) => sum + j.percent, 0) / active.length)
      : 100;
    return { activeJobs: active, terminalJobs: terminal, aggregatePercent: avg };
  }, [jobList]);

  if (!activeGameName || jobList.length === 0) return null;

  const countLabel = activeJobs.length > 0
    ? `${activeJobs.length} download${activeJobs.length !== 1 ? "s" : ""}`
    : `${terminalJobs.length} completed`;

  return (
    <div className="shrink-0 animate-slide-up bg-surface-1 border-t border-border">
      <button
        onClick={toggleFooter}
        className="flex w-full items-center gap-3 px-4 h-10 hover:bg-surface-2/50 transition-colors"
      >
        <Download size={16} className="text-accent shrink-0" />
        <span className="text-sm text-text-secondary whitespace-nowrap">{countLabel}</span>
        <div className="flex-1 mx-2 h-1.5 rounded-full bg-surface-3 overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-300",
              aggregatePercent >= 100 ? "bg-success" : "bg-accent",
            )}
            style={{ width: `${Math.min(aggregatePercent, 100)}%` }}
          />
        </div>
        <span className="text-xs text-text-muted tabular-nums whitespace-nowrap">
          {aggregatePercent}%
        </span>
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
          {jobList.map((job) => (
            <div key={job.id} className="animate-fade-in">
              <DownloadProgress
                job={job}
                onCancel={
                  job.status === "pending" || job.status === "downloading"
                    ? () =>
                        cancelDownload.mutate({
                          gameName: activeGameName,
                          jobId: job.id,
                        })
                    : undefined
                }
              />
            </div>
          ))}
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
  );
}
