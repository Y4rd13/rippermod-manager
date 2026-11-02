import type { DeployReport } from "@/hooks/use-deploy";
import { toast } from "@/stores/toast-store";

/** ``skipped_reason`` the backend sends when tools/redmod/bin/redMod.exe is absent. */
export const REDMOD_MISSING_REASON = "REDmod binary not found";

export const REDMOD_MISSING_MESSAGE =
  "REDmod content changed but redMod.exe was not found. REDmods will not load until the REDmod DLC is installed.";

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
  if (report.redmod && !report.redmod.ran && report.redmod.skipped_reason === REDMOD_MISSING_REASON) {
    toast.warning(`${action} complete, REDmod not compiled`, REDMOD_MISSING_MESSAGE);
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
