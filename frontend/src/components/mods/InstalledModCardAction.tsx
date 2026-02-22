import { Power, PowerOff, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

interface Props {
  disabled: boolean;
  isToggling: boolean;
  isUninstalling: boolean;
  onToggle: () => void;
  onUninstall: () => void;
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

      {confirmAction === "disable" && (
        <ConfirmDialog
          title="Disable Mod?"
          message="This mod's files will be renamed and it won't load in-game."
          confirmLabel="Disable"
          variant="warning"
          icon={PowerOff}
          loading={isToggling}
          onConfirm={() => {
            onToggle();
            setConfirmAction(null);
          }}
          onCancel={() => setConfirmAction(null)}
        />
      )}

      {confirmAction === "enable" && (
        <ConfirmDialog
          title="Enable Mod?"
          message="This mod's files will be restored and it will load in-game."
          confirmLabel="Enable"
          variant="warning"
          icon={Power}
          loading={isToggling}
          onConfirm={() => {
            onToggle();
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
          onConfirm={() => {
            onUninstall();
            setConfirmAction(null);
          }}
          onCancel={() => setConfirmAction(null)}
        />
      )}
    </div>
  );
}
