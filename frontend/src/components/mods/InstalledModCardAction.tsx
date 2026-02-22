import { Power, PowerOff, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";

interface Props {
  disabled: boolean;
  isToggling: boolean;
  isUninstalling: boolean;
  onToggle: () => void;
  onUninstall: () => void;
}

export function InstalledModCardAction({
  disabled,
  isToggling,
  isUninstalling,
  onToggle,
  onUninstall,
}: Props) {
  const [confirming, setConfirming] = useState(false);

  const stop = (e: React.MouseEvent) => e.stopPropagation();

  return (
    <div className="flex items-center gap-1" onClick={stop}>
      <Button
        variant="ghost"
        size="sm"
        title={disabled ? "Enable this mod" : "Disable this mod"}
        loading={isToggling}
        onClick={onToggle}
      >
        {disabled ? (
          <Power size={14} className="text-success" />
        ) : (
          <PowerOff size={14} className="text-warning" />
        )}
      </Button>
      {confirming ? (
        <Button
          variant="danger"
          size="sm"
          loading={isUninstalling}
          onClick={() => {
            onUninstall();
            setConfirming(false);
          }}
        >
          Confirm
        </Button>
      ) : (
        <Button
          variant="ghost"
          size="sm"
          title="Uninstall this mod"
          onClick={() => setConfirming(true)}
        >
          <Trash2 size={14} className="text-danger" />
        </Button>
      )}
    </div>
  );
}
