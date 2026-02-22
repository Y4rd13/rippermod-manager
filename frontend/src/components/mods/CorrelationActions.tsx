import { CheckCircle, Pencil, XCircle } from "lucide-react";
import { useState } from "react";

import { useConfirmCorrelation, useRejectCorrelation } from "@/hooks/mutations";
import { cn } from "@/lib/utils";

import { ReassignDialog } from "./ReassignDialog";

interface Props {
  gameName: string;
  modGroupId: number;
  confirmed: boolean;
}

export function CorrelationActions({ gameName, modGroupId, confirmed }: Props) {
  const [showReassign, setShowReassign] = useState(false);
  const confirm = useConfirmCorrelation();
  const reject = useRejectCorrelation();

  return (
    <>
      <div className="inline-flex items-center gap-1">
        <button
          type="button"
          title={confirmed ? "Match confirmed" : "Accept match"}
          disabled={confirmed || confirm.isPending}
          onClick={(e) => {
            e.stopPropagation();
            confirm.mutate({ gameName, modGroupId });
          }}
          className={cn(
            "rounded p-1 transition-colors",
            confirmed
              ? "text-success cursor-default"
              : "text-text-muted hover:text-success hover:bg-success/10",
          )}
        >
          <CheckCircle size={14} />
        </button>
        <button
          type="button"
          title="Reject match"
          disabled={reject.isPending}
          onClick={(e) => {
            e.stopPropagation();
            if (window.confirm("Remove this Nexus match? The mod will appear as unmatched.")) {
              reject.mutate({ gameName, modGroupId });
            }
          }}
          className="rounded p-1 text-text-muted transition-colors hover:text-danger hover:bg-danger/10"
        >
          <XCircle size={14} />
        </button>
        <button
          type="button"
          title="Correct match"
          onClick={(e) => {
            e.stopPropagation();
            setShowReassign(true);
          }}
          className="rounded p-1 text-text-muted transition-colors hover:text-accent hover:bg-accent/10"
        >
          <Pencil size={14} />
        </button>
      </div>

      {showReassign && (
        <ReassignDialog
          gameName={gameName}
          modGroupId={modGroupId}
          onClose={() => setShowReassign(false)}
        />
      )}
    </>
  );
}
