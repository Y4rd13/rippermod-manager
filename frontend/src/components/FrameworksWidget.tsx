import { openUrl } from "@tauri-apps/plugin-opener";
import { AlertTriangle, Ban, Boxes, CheckCircle2, CircleDashed, Clock, ExternalLink } from "lucide-react";

import { useFrameworks } from "@/hooks/queries";

/**
 * Framework monitor: install status + version of the core Cyberpunk modding
 * frameworks (RED4ext, redscript, ArchiveXL, TweakXL, Codeware, CET), flagging
 * missing and outdated ones. redscript has no on-disk version, so it shows as
 * installed with an unknown version.
 */
export function FrameworksWidget({ gameName }: { gameName: string }) {
  const { data, isLoading } = useFrameworks(gameName);

  if (isLoading || !data) return null;

  const installed = data.filter((f) => f.installed).length;
  const outdated = data.filter((f) => f.outdated).length;

  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-text-primary">
        <Boxes size={15} className="shrink-0 text-accent" />
        Frameworks
        <span className="ml-auto text-xs font-normal text-text-muted">
          {installed}/{data.length} installed
          {outdated > 0 && (
            <>
              {" · "}
              <span className="text-warning">{outdated} outdated</span>
            </>
          )}
        </span>
      </div>
      <ul className="space-y-1.5">
        {data.map((fw) => {
          const label =
            fw.manager_status === "disabled"
              ? "disabled"
              : fw.manager_status === "deploy_pending"
                ? "installed, not deployed"
                : fw.manager_status === "not_installed"
                  ? "not installed"
                  : fw.version_known
                    ? `v${fw.version}`
                    : "installed (version unknown)";
          return (
            <li key={fw.key} className="flex items-center gap-2 text-xs">
              {fw.outdated ? (
                <AlertTriangle size={14} className="shrink-0 text-warning" />
              ) : fw.manager_status === "active" ? (
                <CheckCircle2 size={14} className="shrink-0 text-accent" />
              ) : fw.manager_status === "disabled" ? (
                <Ban size={14} className="shrink-0 text-text-muted" />
              ) : fw.manager_status === "deploy_pending" ? (
                <Clock size={14} className="shrink-0 text-warning" />
              ) : (
                <CircleDashed size={14} className="shrink-0 text-text-muted" />
              )}
              <span className="font-medium text-text-primary">{fw.name}</span>
              <span className="text-text-muted">{label}</span>
              {fw.outdated && fw.latest_version && (
                <span
                  className="text-warning"
                  title={fw.latest_is_cached ? "Latest known version (cached, may be stale)" : undefined}
                >
                  &rarr; v{fw.latest_version}
                  {fw.latest_is_cached && " *"}
                </span>
              )}
              <button
                type="button"
                onClick={() => void openUrl(fw.nexus_url)}
                title={`${fw.name} on Nexus Mods`}
                className="ml-auto inline-flex shrink-0 items-center text-text-muted hover:text-text-secondary"
              >
                <ExternalLink size={12} />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
