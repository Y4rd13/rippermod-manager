import { AlertTriangle, CheckCircle, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { useDeploy, useDeployStatus } from "@/hooks/use-deploy";

interface DeployStatusBadgeProps {
  gameName: string | null;
}

export function DeployStatusBadge({ gameName }: DeployStatusBadgeProps) {
  const { data: status } = useDeployStatus(gameName);
  const deploy = useDeploy(gameName);

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

  return (
    <div className="inline-flex items-center gap-2 text-xs">
      <span className="inline-flex items-center gap-1 text-warning">
        <AlertTriangle size={14} /> Drift: {status.missing} missing
      </span>
      <Button
        size="sm"
        variant="secondary"
        loading={deploy.isPending}
        onClick={() => deploy.mutate()}
      >
        <RotateCcw size={12} /> Redeploy
      </Button>
    </div>
  );
}
