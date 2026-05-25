import { openUrl } from "@tauri-apps/plugin-opener";
import { AlertTriangle, ArrowRight, Ban, Boxes, Check, CircleDashed, Clock, ExternalLink } from "lucide-react";

import { useFrameworks } from "@/hooks/queries";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";
import type { FrameworkStatus } from "@/types/api";

type AttentionKind = "outdated" | "disabled" | "not_installed" | "deploy_pending";

/** Why a framework needs attention, or null if it's active and current. */
function attentionKind(f: FrameworkStatus): AttentionKind | null {
  if (f.manager_status === "not_installed") return "not_installed";
  if (f.manager_status === "disabled") return "disabled";
  if (f.outdated) return "outdated";
  if (f.manager_status === "deploy_pending") return "deploy_pending";
  return null;
}

/**
 * Framework monitor panel: install status + version of the core Cyberpunk
 * modding frameworks (RED4ext, redscript, ArchiveXL, TweakXL, Codeware, CET).
 * Splits the list so the ones needing attention (missing / disabled / outdated
 * / not-yet-deployed) surface as prominent, actionable rows, while the healthy
 * ones collapse into compact chips. redscript has no on-disk version, so it
 * reads as installed with an unknown version.
 */
export function FrameworksWidget({ gameName }: { gameName: string }) {
  const { data, isLoading } = useFrameworks(gameName);

  if (isLoading || !data) return null;

  const needsAttention = data.filter((f) => attentionKind(f) !== null);
  const upToDate = data.filter((f) => attentionKind(f) === null);
  const installed = data.filter((f) => f.installed).length;
  const outdated = data.filter((f) => f.outdated).length;

  return (
    <div className="rounded-xl border border-border bg-surface-1 p-4">
      <div className="flex items-center gap-2">
        <Boxes size={16} className="shrink-0 text-accent" />
        <h3 className="text-sm font-semibold text-text-primary">Frameworks</h3>
        <span className="ml-auto flex items-center gap-2 text-xs text-text-muted">
          <span>
            {installed}/{data.length} installed
          </span>
          {outdated > 0 && <Badge variant="warning">{outdated} outdated</Badge>}
        </span>
      </div>
      <p className="mt-1 text-xs text-text-muted">
        Core mods most others depend on — keep them current, especially right after a Cyberpunk patch.
      </p>

      {needsAttention.length > 0 && (
        <div className="mt-3 space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Needs attention</p>
          {needsAttention.map((fw) => (
            <FrameworkRow key={fw.key} fw={fw} />
          ))}
        </div>
      )}

      {upToDate.length > 0 && (
        <div className="mt-3">
          {needsAttention.length > 0 && (
            <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-muted">Up to date</p>
          )}
          <div className="flex flex-wrap gap-1.5">
            {upToDate.map((fw) => (
              <button
                key={fw.key}
                type="button"
                onClick={() => void openUrl(fw.nexus_url)}
                title={`${fw.name}${fw.version_known && fw.version ? ` v${fw.version}` : " (version unknown)"} — open on Nexus`}
                className="inline-flex items-center gap-1 rounded-full border border-success/20 bg-success/10 px-2 py-0.5 text-xs text-success transition-colors hover:bg-success/20"
              >
                <Check size={11} className="shrink-0" />
                {fw.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FrameworkRow({ fw }: { fw: FrameworkStatus }) {
  const kind = attentionKind(fw);
  const danger = kind === "disabled" || kind === "not_installed";
  const Icon =
    kind === "outdated"
      ? AlertTriangle
      : kind === "deploy_pending"
        ? Clock
        : kind === "disabled"
          ? Ban
          : CircleDashed;

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border border-l-2 border-border bg-surface-2 px-3 py-2",
        danger ? "border-l-danger/70" : "border-l-warning/70",
      )}
    >
      <Icon size={14} className={cn("shrink-0", danger ? "text-danger" : "text-warning")} />
      <span className="text-sm font-medium text-text-primary">{fw.name}</span>
      {fw.version_known && fw.version && <span className="text-xs text-text-muted">v{fw.version}</span>}
      {kind === "outdated" && (
        <>
          <ArrowRight size={12} className="shrink-0 text-text-muted" />
          <Badge
            variant="warning"
            title={fw.latest_is_cached ? "Latest known version (cached, may be stale)" : "Update available on Nexus"}
          >
            ↑ v{fw.latest_version}
            {fw.latest_is_cached ? " *" : ""}
          </Badge>
        </>
      )}
      {kind === "not_installed" && <Badge variant="danger">Not installed</Badge>}
      {kind === "disabled" && <Badge variant="danger">Disabled</Badge>}
      {kind === "deploy_pending" && <Badge variant="warning">Not deployed</Badge>}
      <button
        type="button"
        onClick={() => void openUrl(fw.nexus_url)}
        title={`${fw.name} on Nexus Mods`}
        className="ml-auto inline-flex shrink-0 items-center text-text-muted hover:text-text-secondary"
      >
        <ExternalLink size={13} />
      </button>
    </div>
  );
}
