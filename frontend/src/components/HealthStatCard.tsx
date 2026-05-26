import { AlertTriangle, CircleAlert, HeartPulse } from "lucide-react";

import { useHealth } from "@/hooks/queries";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { HealthReport } from "@/types/api";

interface AttentionItem {
  name: string;
  note: string;
  danger: boolean;
}

/**
 * Reduce the health report to an at-a-glance summary for the stat card: a
 * worst-case tone, a short label, and the critical/warning issues (for the
 * hover popover). Info-level issues don't drive the headline — they never
 * block a launch.
 */
function summarize(report: HealthReport | undefined) {
  if (!report) return { tone: "success" as const, label: "--", attention: [] as AttentionItem[] };
  const attention: AttentionItem[] = report.issues
    .filter((i) => i.severity === "critical" || i.severity === "warning")
    .map((i) => ({
      name: i.mod_name || "Setup",
      note: i.severity === "critical" ? "critical" : "needs fixing",
      danger: i.severity === "critical",
    }));
  const tone: "danger" | "warning" | "success" =
    report.critical > 0 ? "danger" : report.warning > 0 ? "warning" : "success";
  const label =
    report.critical > 0
      ? `${report.critical} critical`
      : report.warning > 0
        ? `${report.warning} to fix`
        : "Ready";
  return { tone, label, attention };
}

/**
 * Header stat card for the pre-launch health check. Shows a colour-coded
 * at-a-glance status next to Play; on hover reveals which issues need
 * attention; on click jumps to (and highlights) the full panel.
 */
export function HealthStatCard({ gameName, onOpen }: { gameName: string; onOpen: () => void }) {
  const { data, isLoading } = useHealth(gameName);
  const s = summarize(data);
  const iconColor =
    s.tone === "danger" ? "text-danger" : s.tone === "warning" ? "text-warning" : "text-success";
  const hoverBorder =
    s.tone === "danger"
      ? "hover:border-danger/40"
      : s.tone === "warning"
        ? "hover:border-warning/40"
        : "hover:border-success/40";

  return (
    <Card
      className={cn("group relative transition-colors", hoverBorder)}
      onClick={onOpen}
      title={
        s.attention.length > 0
          ? "Pre-launch check found issues — click for details and one-click fixes"
          : "Pre-launch check — no blocking issues found"
      }
    >
      <div className="flex items-center gap-3">
        <HeartPulse size={18} className={cn("shrink-0", iconColor)} />
        <div>
          <p className="text-xs text-text-muted">Health</p>
          <p className="text-lg font-bold text-text-primary">{isLoading ? "--" : s.label}</p>
        </div>
      </div>

      {/* Hover/focus popover: which issues need attention. Info only. */}
      {s.attention.length > 0 && (
        <div className="pointer-events-none absolute right-0 top-full z-30 mt-2 w-64 rounded-lg border border-border bg-surface-2 p-3 text-left opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Needs attention
          </p>
          <ul className="space-y-1.5">
            {s.attention.slice(0, 6).map((a, i) => {
              const Icon = a.danger ? CircleAlert : AlertTriangle;
              return (
                <li key={i} className="flex items-center gap-2 text-xs">
                  <Icon size={12} className={cn("shrink-0", a.danger ? "text-danger" : "text-warning")} />
                  <span className="min-w-0 truncate font-medium text-text-primary">{a.name}</span>
                  <span className={cn("ml-auto whitespace-nowrap", a.danger ? "text-danger" : "text-warning")}>
                    {a.note}
                  </span>
                </li>
              );
            })}
            {s.attention.length > 6 && (
              <li className="text-[11px] text-text-muted">+{s.attention.length - 6} more</li>
            )}
          </ul>
          <p className="mt-2 text-[10px] text-text-muted">Click to view details</p>
        </div>
      )}
    </Card>
  );
}
