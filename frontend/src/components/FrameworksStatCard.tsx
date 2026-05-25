import { AlertTriangle, Boxes } from "lucide-react";

import { useFrameworks } from "@/hooks/queries";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { FrameworkStatus } from "@/types/api";

interface AttentionItem {
  name: string;
  note: string;
  danger: boolean;
}

/**
 * Reduce the framework list to an at-a-glance summary: a worst-case tone, a
 * short label for the stat card, and the list of frameworks needing attention
 * (used by the hover popover). Missing/disabled are critical (won't load);
 * outdated/deploy-pending are warnings.
 */
function summarize(frameworks: FrameworkStatus[]) {
  const attention: AttentionItem[] = [];
  let missing = 0;
  let disabled = 0;
  let outdated = 0;
  let pending = 0;
  // Classify each framework once (severity order) and tally in the same pass so
  // the counts stay consistent with attention.length even when a framework
  // matches several states (e.g. disabled AND outdated → counted once).
  for (const f of frameworks) {
    if (f.manager_status === "not_installed") {
      attention.push({ name: f.name, note: "not installed", danger: true });
      missing++;
    } else if (f.manager_status === "disabled") {
      attention.push({ name: f.name, note: "disabled", danger: true });
      disabled++;
    } else if (f.outdated) {
      attention.push({ name: f.name, note: f.latest_version ? `→ v${f.latest_version}` : "update available", danger: false });
      outdated++;
    } else if (f.manager_status === "deploy_pending") {
      attention.push({ name: f.name, note: "not deployed", danger: false });
      pending++;
    }
  }
  const parts: string[] = [];
  if (missing) parts.push(`${missing} missing`);
  if (disabled) parts.push(`${disabled} disabled`);
  if (outdated) parts.push(`${outdated} outdated`);
  if (pending) parts.push(`${pending} to deploy`);
  const count = attention.length;
  const tone: "danger" | "warning" | "success" = missing || disabled ? "danger" : count ? "warning" : "success";
  const label =
    count === 0 ? "All OK" : parts.length === 1 ? parts.join(", ") : `${count} ${count === 1 ? "issue" : "issues"}`;
  return { count, tone, label, detail: parts.join(", "), attention };
}

/**
 * Header stat card for the core modding frameworks. Shows a colour-coded
 * at-a-glance status next to Play; on hover reveals which frameworks need
 * attention; on click jumps to (and highlights) the full panel.
 */
export function FrameworksStatCard({ gameName, onOpen }: { gameName: string; onOpen: () => void }) {
  const { data: frameworks = [], isLoading } = useFrameworks(gameName);
  const s = summarize(frameworks);
  const iconColor =
    s.tone === "danger" ? "text-danger" : s.tone === "warning" ? "text-warning" : "text-success";
  const hoverBorder =
    s.tone === "danger"
      ? "hover:border-danger/40"
      : s.tone === "warning"
        ? "hover:border-warning/40"
        : "hover:border-success/40";

  return (
    <Card
      className={cn("group relative transition-colors", hoverBorder)}
      onClick={onOpen}
      title={
        s.count > 0
          ? `Frameworks needing attention: ${s.detail}`
          : "Core modding frameworks (RED4ext, redscript, ArchiveXL, TweakXL, Codeware, CET) — all installed and current"
      }
    >
      <div className="flex items-center gap-3">
        <Boxes size={18} className={cn("shrink-0", iconColor)} />
        <div>
          <p className="text-xs text-text-muted">Frameworks</p>
          <p className="text-lg font-bold text-text-primary">{isLoading ? "--" : s.label}</p>
        </div>
      </div>

      {/* Hover/focus popover: which frameworks need attention. Info only. */}
      {s.attention.length > 0 && (
        <div className="pointer-events-none absolute right-0 top-full z-30 mt-2 w-64 rounded-lg border border-border bg-surface-2 p-3 text-left opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Needs attention
          </p>
          <ul className="space-y-1.5">
            {s.attention.map((a) => (
              <li key={a.name} className="flex items-center gap-2 text-xs">
                <AlertTriangle size={12} className={cn("shrink-0", a.danger ? "text-danger" : "text-warning")} />
                <span className="font-medium text-text-primary">{a.name}</span>
                <span className={cn("ml-auto whitespace-nowrap", a.danger ? "text-danger" : "text-warning")}>
                  {a.note}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[10px] text-text-muted">Click to view details</p>
        </div>
      )}
    </Card>
  );
}
