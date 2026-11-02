import { ExternalLink } from "lucide-react";
import { openUrl } from "@tauri-apps/plugin-opener";

import { type AppUpdateState } from "@/hooks/use-app-update-check";
import { cn } from "@/lib/utils";

interface Props {
  update: AppUpdateState;
  size?: "sm" | "md";
}

/**
 * Actions block shared by the top banner and the Settings notice.
 *
 * The Nexus edition never downloads its own installer: every user gets the
 * RipperMod Files tab on Nexus and installs the new version from there.
 */
export function AppUpdateActions({ update, size = "md" }: Props) {
  const handleGetOnNexus = () => {
    void openUrl(update.nexusFilesUrl);
  };

  const accentBtn = cn(
    "inline-flex shrink-0 items-center gap-1 rounded-md border font-medium transition-colors",
    size === "sm" ? "px-2 py-1 text-xs" : "px-2.5 py-1 text-xs",
    "border-accent/40 bg-accent/15 text-accent hover:bg-accent/25",
  );

  return (
    <button type="button" onClick={handleGetOnNexus} className={accentBtn}>
      <ExternalLink size={12} /> Get on Nexus
    </button>
  );
}
