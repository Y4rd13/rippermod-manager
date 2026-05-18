import { AlertTriangle, CheckCircle, RotateCcw, Zap } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useDeploy, useDeployStatus } from "@/hooks/use-deploy";
import { reportDeployOutcome } from "@/lib/deploy-toast";
import { toast } from "@/stores/toast-store";

interface DeployStatusBadgeProps {
  gameName: string | null;
}

export function DeployStatusBadge({ gameName }: DeployStatusBadgeProps) {
  const { data: status } = useDeployStatus(gameName);
  const deploy = useDeploy(gameName);
  const [confirmForce, setConfirmForce] = useState(false);

  const runDeploy = (force: boolean) => {
    deploy.mutate(
      { force },
      {
        onSuccess: (report) =>
          reportDeployOutcome(report, force ? "Force redeploy" : "Redeploy"),
        onError: (error) =>
          toast.error(force ? "Force redeploy failed" : "Redeploy failed", error.message),
        onSettled: () => setConfirmForce(false),
      },
    );
  };

  const handleRedeploy = () => {
    // When the only drift is missing links (no foreign squatters), a normal
    // redeploy is enough. When foreign files are in the way, prompt for
    // confirmation since overwriting is destructive.
    if (status && status.foreign > 0) {
      setConfirmForce(true);
      return;
    }
    runDeploy(false);
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
    <>
      <div className="inline-flex items-center gap-2 text-xs">
        <span className="inline-flex items-center gap-1 text-warning">
          <AlertTriangle size={14} /> Drift: {driftLabel}
        </span>
        <Button size="sm" loading={deploy.isPending} onClick={handleRedeploy}>
          <RotateCcw size={12} /> Redeploy
        </Button>
      </div>

      {confirmForce && status.foreign > 0 && (
        <ConfirmDialog
          title="Overwrite foreign files?"
          message={
            `${status.foreign} file${status.foreign === 1 ? "" : "s"} in the game folder are currently ` +
            `copies (not RipperMod hardlinks), most likely left over from another mod manager or a ` +
            `manual install. A regular redeploy refuses to overwrite them. Force redeploy will delete ` +
            `each of those files and replace them with RipperMod hardlinks. Your staged copies in ` +
            `downloaded_mods/ are not touched, so this is safe to undo by uninstalling. ` +
            `Close Cyberpunk 2077 first.`
          }
          confirmLabel="Force redeploy"
          variant="warning"
          icon={Zap}
          loading={deploy.isPending}
          onConfirm={() => runDeploy(true)}
          onCancel={() => setConfirmForce(false)}
        />
      )}
    </>
  );
}
