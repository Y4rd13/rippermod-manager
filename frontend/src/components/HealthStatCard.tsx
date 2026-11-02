import type { StatusVerdict } from "@/components/FrameworksStatCard";
import { useHealth } from "@/hooks/queries";
import type { HealthReport } from "@/types/api";

interface AttentionItem {
  name: string;
  note: string;
  danger: boolean;
}

/**
 * Reduce the health report to an at-a-glance summary for the status strip: a
 * worst-case tone, a short label, and the critical/warning issues (for the
 * item's title). Info-level issues don't drive the headline — they never
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
 * Verdict for the pre-launch health check, shown as one item of the game status strip.
 * The title names the issues that need attention (up to six), as the old popover did.
 */
export function useHealthVerdict(gameName: string): StatusVerdict {
  const { data, isLoading } = useHealth(gameName);
  const s = summarize(data);
  const shown = s.attention.slice(0, 6).map((a) => `${a.name} (${a.note})`);
  const more = s.attention.length > 6 ? `, +${s.attention.length - 6} more` : "";
  return {
    value: isLoading ? "--" : s.label,
    tone: s.tone,
    title:
      s.attention.length > 0
        ? `Pre-launch check found issues: ${shown.join(", ")}${more}. Click for details and one-click fixes`
        : "Pre-launch check complete, no blocking issues found",
  };
}
