import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export interface ScanLog {
  phase: string;
  message: string;
  percent: number;
}

const PHASE_LABELS: Record<string, string> = {
  scan: "Scanning files",
  group: "Grouping mods",
  index: "Indexing",
  fomod: "Reading archive metadata",
  enrich: "Enriching mod data",
  md5: "Matching archives",
  sync: "Syncing Nexus",
  correlate: "Correlating mods",
  "web-search": "Web search",
  done: "Complete",
  error: "Error",
  complete: "Finishing",
};

export function ScanProgress({
  logs,
  percent,
  phase,
}: {
  logs: ScanLog[];
  percent: number;
  phase: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (expanded && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs.length, expanded]);

  const isDone = phase === "done" || phase === "complete";

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-text-secondary font-medium">
            {PHASE_LABELS[phase] ?? phase}
          </span>
          <span className="text-text-muted tabular-nums">{percent}%</span>
        </div>
        <div className="h-1.5 w-full rounded-full bg-surface-3 overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-300 ease-out",
              isDone ? "bg-success" : "bg-accent",
            )}
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      {logs.length > 0 && (
        <div className="rounded-lg border border-border bg-surface-1 overflow-hidden">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="flex w-full items-center justify-between px-3 py-2 text-xs text-text-muted hover:text-text-secondary transition-colors"
          >
            <span>{logs.length} log entries</span>
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 transition-transform duration-200",
                expanded && "rotate-180",
              )}
            />
          </button>
          <div
            className={cn(
              "overflow-hidden transition-all duration-200 ease-out",
              expanded ? "max-h-48" : "max-h-0",
            )}
          >
            <div ref={scrollRef} className="overflow-y-auto max-h-48 border-t border-border">
              {logs.slice(-50).map((log, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 px-3 py-1 text-[11px] font-mono leading-relaxed"
                >
                  <span
                    className={cn(
                      "shrink-0 mt-0.5 h-1.5 w-1.5 rounded-full",
                      log.phase === "error"
                        ? "bg-danger"
                        : log.phase === "done"
                          ? "bg-success"
                          : "bg-accent/60",
                    )}
                  />
                  <span className="text-text-muted break-all">{log.message}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
