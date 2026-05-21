import { Sparkles } from "lucide-react";

import { AppUpdateActions } from "@/components/AppUpdateActions";
import { useAppUpdateCheck } from "@/hooks/use-app-update-check";

/**
 * Top-of-app banner. Renders whenever the latest Nexus version is strictly
 * newer than the running build. Not dismissible — it stays until the user
 * actually installs the new version (the binary version match makes the
 * banner disappear automatically).
 */
export function AppUpdateBanner() {
  const update = useAppUpdateCheck();

  if (!update.hasUpdate) return null;

  return (
    <div className="flex items-center justify-between gap-3 border-b border-accent/30 bg-accent/10 px-4 py-2 text-sm">
      <div className="flex items-center gap-2 text-text-primary min-w-0">
        <Sparkles size={14} className="shrink-0 text-accent" />
        <span className="truncate">
          <strong className="font-semibold">RipperMod Manager v{update.latestVersion}</strong>{" "}
          is available on Nexus Mods.
        </span>
      </div>
      <AppUpdateActions update={update} size="sm" />
    </div>
  );
}
