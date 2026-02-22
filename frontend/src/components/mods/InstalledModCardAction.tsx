import { Power, PowerOff, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

interface Props {
  disabled: boolean;
  isToggling: boolean;
  isUninstalling: boolean;
  onToggle: () => Promise<unknown>;
  onUninstall: () => Promise<unknown>;
}

type ConfirmAction = "disable" | "enable" | "uninstall" | null;

export function InstalledModCardAction({
  disabled,
  isToggling,
  isUninstalling,
  onToggle,
  onUninstall,
}: Props) {
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null);

  const stop = (e: React.MouseEvent) => e.stopPropagation();

  return (
    <div className="flex items-center gap-1" onClick={stop}>
      <Button
        variant="ghost"
        size="sm"
        title={disabled ? "Enable this mod" : "Disable this mod"}
        loading={isToggling}
        onClick={() => setConfirmAction(disabled ? "enable" : "disable")}
      >
        {disabled ? (
          <Power size={14} className="text-success" />
        ) : (
          <PowerOff size={14} className="text-warning" />
        )}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        title="Uninstall this mod"
        onClick={() => setConfirmAction("uninstall")}
      >
        <Trash2 size={14} className="text-danger" />
      </Button>

      {(confirmAction === "disable" || confirmAction === "enable") && (
        <ConfirmDialog
          title={confirmAction === "disable" ? "Disable Mod?" : "Enable Mod?"}
          message={
            confirmAction === "disable"
              ? "This mod's files will be renamed and it won't load in-game."
              : "This mod's files will be restored and it will load in-game."
          }
          confirmLabel={confirmAction === "disable" ? "Disable" : "Enable"}
          variant="warning"
          icon={confirmAction === "disable" ? PowerOff : Power}
          loading={isToggling}
          onConfirm={async () => {
            await onToggle();
            setConfirmAction(null);
          }}
          onCancel={() => setConfirmAction(null)}
        />
      )}

      {confirmAction === "uninstall" && (
        <ConfirmDialog
          title="Uninstall Mod?"
          message="All installed files for this mod will be permanently deleted."
          confirmLabel="Uninstall"
          variant="danger"
          icon={Trash2}
          loading={isUninstalling}
          onConfirm={async () => {
            await onUninstall();
            setConfirmAction(null);
          }}
          onCancel={() => setConfirmAction(null)}
        />
      )}
    </div>
  );
}
