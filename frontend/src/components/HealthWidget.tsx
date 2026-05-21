import { AlertTriangle, CircleAlert, Info, ShieldCheck } from "lucide-react";

import { useHealth } from "@/hooks/queries";

const SEVERITY_RANK: Record<string, number> = { critical: 0, warning: 1, info: 2 };

const SEVERITY_STYLE: Record<string, { color: string; Icon: typeof Info }> = {
  critical: { color: "text-danger", Icon: CircleAlert },
  warning: { color: "text-warning", Icon: AlertTriangle },
  info: { color: "text-text-muted", Icon: Info },
};

/**
 * Pre-launch health check: lists requirement, install, version, and foreign-file
 * problems for a game, each with the affected mod and a suggested fix.
 */
export function HealthWidget({ gameName }: { gameName: string }) {
  const { data, isLoading } = useHealth(gameName);

  if (isLoading || !data) return null;

  if (data.issues.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-sm text-text-secondary">
        <ShieldCheck size={16} className="shrink-0 text-accent" />
        No issues found — your setup looks ready to launch.
      </div>
    );
  }

  const sorted = [...data.issues].sort(
    (a, b) => (SEVERITY_RANK[a.severity] ?? 9) - (SEVERITY_RANK[b.severity] ?? 9),
  );

  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-text-primary">
        <AlertTriangle size={15} className="shrink-0 text-warning" />
        Pre-launch check
        <span className="ml-auto text-xs font-normal text-text-muted">
          {data.critical > 0 && <span className="text-danger">{data.critical} critical</span>}
          {data.critical > 0 && data.warning + data.info > 0 && " · "}
          {data.warning > 0 && <span className="text-warning">{data.warning} warning</span>}
          {data.warning > 0 && data.info > 0 && " · "}
          {data.info > 0 && <span>{data.info} info</span>}
        </span>
      </div>
      <ul className="max-h-72 space-y-1.5 overflow-y-auto">
        {sorted.map((issue, i) => {
          const style = SEVERITY_STYLE[issue.severity] ?? { color: "text-text-muted", Icon: Info };
          const Icon = style.Icon;
          return (
            <li key={i} className="flex gap-2 text-xs">
              <Icon size={14} className={`mt-0.5 shrink-0 ${style.color}`} />
              <div className="min-w-0">
                <p className="text-text-secondary">
                  {issue.mod_name && (
                    <span className="font-medium text-text-primary">{issue.mod_name}</span>
                  )}
                  {issue.mod_name ? " " : ""}
                  {issue.message}
                </p>
                {issue.suggested_fix && (
                  <p className="text-text-muted">→ {issue.suggested_fix}</p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
