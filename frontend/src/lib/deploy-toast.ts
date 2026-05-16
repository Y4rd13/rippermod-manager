import type { DeployReport } from "@/hooks/use-deploy";
import { toast } from "@/stores/toast-store";

/**
 * Shared toast helper for deploy-style operations (Deploy, Undeploy, Redeploy).
 *
 * Splits the three meaningful outcomes — preflight refusal, partial failure of
 * hardlink/junction ops, and (success + REDmod compile status) — into distinct
 * toasts so the user always sees what actually happened. REDmod compile failure
 * after a clean link pass is shown as an error because the game would still load
 * with stale scripts even though every file op succeeded.
 */
export function reportDeployOutcome(report: DeployReport, action: string): void {
  if (report.preflight && !report.preflight.ok) {
    toast.error(
      `${action} refused`,
      report.preflight.reasons.join(" ") || "Pre-flight check failed",
    );
    return;
  }
  if (report.failed > 0) {
    toast.error(
      `${action} failed`,
      `${report.failed} of ${report.total} operations failed`,
    );
    return;
  }
  if (report.redmod && report.redmod.ran && !report.redmod.success) {
    toast.error(
      `${action} partial`,
      `Files linked but REDmod compile failed: ${report.redmod.error || "unknown error"}`,
    );
    return;
  }
  const skipped = report.skipped_existing
    ? ` (${report.skipped_existing} already current)`
    : "";
  const redmodNote = report.redmod?.success ? " · REDmod compiled" : "";
  toast.success(
    `${action} complete`,
    `${report.done} operation(s) succeeded${skipped}${redmodNote}`,
  );
}
