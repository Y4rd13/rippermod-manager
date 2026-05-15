import { AlertTriangle, CheckCircle, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { type DeployReport, useDeploy, useDeployStatus } from "@/hooks/use-deploy";
import { toast } from "@/stores/toast-store";

interface DeployStatusBadgeProps {
  gameName: string | null;
}

function reportDeployOutcome(report: DeployReport, action: string): void {
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
  const skipped = report.skipped_existing
    ? ` (${report.skipped_existing} already current)`
    : "";
  toast.success(`${action} complete`, `${report.done} operation(s) succeeded${skipped}`);
}

export function DeployStatusBadge({ gameName }: DeployStatusBadgeProps) {
  const { data: status } = useDeployStatus(gameName);
  const deploy = useDeploy(gameName);

  const handleRedeploy = () => {
    deploy.mutate(undefined, {
      onSuccess: (report) => reportDeployOutcome(report, "Redeploy"),
      onError: (error) => toast.error("Redeploy failed", error.message),
    });
  };

  if (!status) return null;

  if (status.total === 0) {
    return <span className="text-xs text-text-muted">No mods deployed</span>;
  }

  if (status.missing === 0 && status.foreign === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-success">
        <CheckCircle size={14} /> Deployed ({status.linked})
      </span>
    );
  }

  const parts: string[] = [];
  if (status.missing > 0) parts.push(`${status.missing} missing`);
  if (status.foreign > 0) parts.push(`${status.foreign} foreign`);
  const driftLabel = parts.length > 0 ? parts.join(", ") : "drifted";

  return (
    <div className="inline-flex items-center gap-2 text-xs">
      <span className="inline-flex items-center gap-1 text-warning">
        <AlertTriangle size={14} /> Drift: {driftLabel}
      </span>
      <Button size="sm" variant="secondary" loading={deploy.isPending} onClick={handleRedeploy}>
        <RotateCcw size={12} /> Redeploy
      </Button>
    </div>
  );
}
