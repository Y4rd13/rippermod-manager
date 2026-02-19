import { X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { DownloadJobOut } from "@/types/api";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / k ** i).toFixed(1)} ${sizes[i]}`;
}

const statusColors: Record<string, string> = {
  pending: "bg-text-muted",
  downloading: "bg-accent",
  completed: "bg-success",
  failed: "bg-danger",
  cancelled: "bg-text-muted",
};

interface DownloadProgressProps {
  job: DownloadJobOut;
  onCancel?: () => void;
}

export function DownloadProgress({ job, onCancel }: DownloadProgressProps) {
  const isActive = job.status === "pending" || job.status === "downloading";
  const barColor = statusColors[job.status] ?? "bg-accent";

  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="truncate text-text-secondary" title={job.file_name}>
            {job.file_name || "Preparing..."}
          </span>
          <span className="text-text-muted ml-2 whitespace-nowrap">
            {job.status === "downloading" && job.total_bytes > 0
              ? `${formatBytes(job.progress_bytes)}/${formatBytes(job.total_bytes)}`
              : job.status === "completed"
                ? "Done"
                : job.status === "failed"
                  ? "Failed"
                  : job.status === "cancelled"
                    ? "Cancelled"
                    : "Pending"}
          </span>
        </div>
        <div className="h-1.5 w-full rounded-full bg-surface-3 overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all duration-300", barColor)}
            style={{ width: `${Math.min(job.percent, 100)}%` }}
          />
        </div>
      </div>
      {isActive && onCancel && (
        <button
          onClick={onCancel}
          className="p-0.5 text-text-muted hover:text-danger transition-colors shrink-0"
          title="Cancel download"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
