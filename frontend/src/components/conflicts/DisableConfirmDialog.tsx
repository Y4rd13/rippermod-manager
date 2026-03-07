import { Power, Trash2 } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { useToggleMod, useUninstallMod } from "@/hooks/mutations";

interface Props {
  gameName: string;
  modId: number;
  modName: string;
  onClose: () => void;
  children?: ReactNode;
}

export function DisableConfirmDialog({ gameName, modId, modName, onClose, children }: Props) {
  const toggleMod = useToggleMod();
  const uninstallMod = useUninstallMod();

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border border-border bg-surface-1 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 mb-4 text-danger">
          <Power size={20} />
          <h3 className="text-lg font-semibold text-text-primary">
            Disable &ldquo;{modName}&rdquo;?
          </h3>
        </div>

        <div className="text-sm text-text-secondary space-y-3 mb-4">
          <p>This will disable the mod and all its archives.</p>
          {children}
          <p className="text-xs text-text-muted">
            The mod can be re-enabled later from the Installed Mods or Archives tab.
            If uninstalled, it can be reinstalled from the Archives tab.
          </p>
        </div>

        <div className="flex justify-end gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={toggleMod.isPending || uninstallMod.isPending}
            onClick={onClose}
          >
            Cancel
          </Button>
          <Button
            variant="danger"
            size="sm"
            loading={uninstallMod.isPending}
            disabled={toggleMod.isPending}
            onClick={() => {
              uninstallMod.mutate(
                { gameName, modId },
                { onSuccess: onClose },
              );
            }}
          >
            <Trash2 size={14} /> Uninstall
          </Button>
          <Button
            variant="danger"
            size="sm"
            loading={toggleMod.isPending}
            disabled={uninstallMod.isPending}
            onClick={() => {
              toggleMod.mutate(
                { gameName, modId },
                { onSuccess: onClose },
              );
            }}
          >
            <Power size={14} /> Disable
          </Button>
        </div>
      </div>
    </div>
  );
}
