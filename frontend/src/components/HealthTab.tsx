import { AlertTriangle, ShieldCheck } from "lucide-react";
import { useEffect, useRef } from "react";

import { FrameworksWidget } from "@/components/FrameworksWidget";
import { HealthWidget } from "@/components/HealthWidget";
import { LogErrorsWidget } from "@/components/LogErrorsWidget";
import { useHealth, useUpdates } from "@/hooks/queries";
import { cn } from "@/lib/utils";

/**
 * The single "is my setup ready to launch?" surface: a readiness banner, the
 * pre-launch check, the core-framework monitor, and the mod error reader — all
 * the launch-readiness signals in one place, so the Installed tab stays about
 * managing mods.
 */
export function HealthTab({
  gameName,
  focusFrameworks,
  onGoToUpdates,
}: {
  gameName: string;
  focusFrameworks: boolean;
  onGoToUpdates: () => void;
}) {
  const { data: health } = useHealth(gameName);
  const { data: updates } = useUpdates(gameName);
  const frameworksRef = useRef<HTMLDivElement>(null);

  // When arrived here via the header "Frameworks" card, scroll its section in.
  useEffect(() => {
    if (focusFrameworks) {
      frameworksRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [focusFrameworks]);

  const critical = health?.critical ?? 0;
  const warning = health?.warning ?? 0;
  const ready = critical === 0;

  return (
    <div className="space-y-4">
      <div
        className={cn(
          "flex items-center gap-2 rounded-xl border px-4 py-3 text-sm text-text-secondary",
          ready ? "border-success/30 bg-success/5" : "border-danger/30 bg-danger/5",
        )}
      >
        {ready ? (
          <ShieldCheck size={18} className="shrink-0 text-success" />
        ) : (
          <AlertTriangle size={18} className="shrink-0 text-danger" />
        )}
        {ready ? (
          "Ready to launch — no critical issues found."
        ) : (
          <span>
            <strong className="text-danger">
              {critical} critical issue{critical === 1 ? "" : "s"}
            </strong>{" "}
            to fix before launching
            {warning > 0 ? ` · ${warning} warning${warning === 1 ? "" : "s"}` : ""}.
          </span>
        )}
      </div>

      <HealthWidget
        gameName={gameName}
        updatesCount={updates?.updates_available ?? 0}
        onGoToUpdates={onGoToUpdates}
      />

      <div
        ref={frameworksRef}
        className={cn(
          "scroll-mt-4 rounded-xl transition-shadow duration-500",
          focusFrameworks && "ring-2 ring-warning ring-offset-2 ring-offset-surface-0",
        )}
      >
        <FrameworksWidget gameName={gameName} />
      </div>

      <LogErrorsWidget gameName={gameName} />
    </div>
  );
}
