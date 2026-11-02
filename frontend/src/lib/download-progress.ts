import type { DownloadStatus } from "@/types/api";

const WAITING: ReadonlySet<DownloadStatus> = new Set(["queued", "pending"]);
const TERMINAL: ReadonlySet<DownloadStatus> = new Set(["completed", "failed", "cancelled"]);

/**
 * Summary for the download queue footer. The percentage averages only the jobs that are
 * actually downloading (null when none are), so jobs waiting in the queue at 0% never drag
 * it down; they are counted in `queued` (queued and pending) instead.
 */
export function summarizeDownloads(jobs: { status: DownloadStatus; percent: number }[]): {
  downloadingPercent: number | null;
  queued: number;
  active: number;
} {
  const downloading = jobs.filter((j) => j.status === "downloading");
  const queued = jobs.filter((j) => WAITING.has(j.status)).length;
  const active = jobs.filter((j) => !TERMINAL.has(j.status)).length;
  const downloadingPercent =
    downloading.length > 0
      ? Math.round(downloading.reduce((sum, j) => sum + j.percent, 0) / downloading.length)
      : null;
  return { downloadingPercent, queued, active };
}
