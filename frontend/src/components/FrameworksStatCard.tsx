import { useFrameworks } from "@/hooks/queries";
import type { FrameworkStatus } from "@/types/api";

interface AttentionItem {
  name: string;
  note: string;
  danger: boolean;
}

/**
 * Reduce the framework list to an at-a-glance summary: a worst-case tone, a
 * short label for the status strip, and the list of frameworks needing attention
 * (listed in the item's title). Missing/disabled are critical (won't load);
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

export interface StatusVerdict {
  value: string;
  tone: "success" | "warning" | "danger";
  title: string;
}

/**
 * Verdict for the core modding frameworks, shown as one item of the game status strip.
 * The title lists which frameworks need attention, so hovering the item tells the same
 * story the old stat card's popover did.
 */
export function useFrameworksVerdict(gameName: string): StatusVerdict {
  const { data: frameworks = [], isLoading } = useFrameworks(gameName);
  const s = summarize(frameworks);
  return {
    value: isLoading ? "--" : s.label,
    tone: s.tone,
    title:
      s.count > 0
        ? `Frameworks needing attention: ${s.attention.map((a) => `${a.name} (${a.note})`).join(", ")}`
        : "Core modding frameworks (RED4ext, redscript, ArchiveXL, TweakXL, Codeware, CET), all installed and current",
  };
}
