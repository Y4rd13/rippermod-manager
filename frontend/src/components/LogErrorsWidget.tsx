import { AlertTriangle, CircleAlert, RefreshCw, ScrollText } from "lucide-react";

import { useLogErrors } from "@/hooks/queries";

/**
 * Mod error reader: warnings/errors parsed from the framework log files
 * (redscript, RED4ext, CET, ArchiveXL, TweakXL, Codeware), grouped by source.
 * Read on demand — the Refresh button re-reads the logs.
 */
export function LogErrorsWidget({ gameName }: { gameName: string }) {
  const { data, isLoading, isFetching, refetch } = useLogErrors(gameName);

  if (isLoading || !data) return null;

  const errors = data.filter((e) => e.level === "error").length;
  const warnings = data.filter((e) => e.level === "warning").length;

  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-text-primary">
        <ScrollText size={15} className="shrink-0 text-accent" />
        Mod errors
        <span className="ml-auto flex items-center gap-2 text-xs font-normal text-text-muted">
          {data.length === 0 ? (
            "no recent errors"
          ) : (
            <span>
              {errors > 0 && (
                <span className="text-danger">
                  {errors} error{errors !== 1 && "s"}
                </span>
              )}
              {errors > 0 && warnings > 0 && " · "}
              {warnings > 0 && (
                <span className="text-warning">
                  {warnings} warning{warnings !== 1 && "s"}
                </span>
              )}
            </span>
          )}
          <button
            type="button"
            onClick={() => void refetch()}
            disabled={isFetching}
            title="Re-read the framework logs"
            className="inline-flex items-center text-text-muted hover:text-text-secondary disabled:opacity-50"
          >
            <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
          </button>
        </span>
      </div>
      {data.length > 0 && (
        <ul className="max-h-72 space-y-1.5 overflow-y-auto">
          {data.map((e, i) => (
            <li key={`${e.source}-${i}`} className="flex gap-2 text-xs">
              {e.level === "error" ? (
                <CircleAlert size={14} className="mt-0.5 shrink-0 text-danger" />
              ) : (
                <AlertTriangle size={14} className="mt-0.5 shrink-0 text-warning" />
              )}
              <div className="min-w-0">
                <span className="mr-1.5 rounded bg-surface-3 px-1.5 py-0.5 text-[10px] font-medium text-text-muted">
                  {e.source}
                </span>
                {e.mod_name && (
                  <span
                    className="mr-1.5 rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-medium text-accent"
                    title="Attributed to this installed mod"
                  >
                    {e.mod_name}
                  </span>
                )}
                <span className="break-words text-text-secondary">{e.message}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
