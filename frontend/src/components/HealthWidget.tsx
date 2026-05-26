import { openUrl } from "@tauri-apps/plugin-opener";
import {
  AlertTriangle,
  ArrowUpCircle,
  ChevronDown,
  CircleAlert,
  ExternalLink,
  HeartPulse,
  Info,
  Power,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { type ComponentType, useState } from "react";

import { useToggleMod } from "@/hooks/mutations";
import { useHealth } from "@/hooks/queries";
import { useDeploy } from "@/hooks/use-deploy";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import type { HealthIssueOut } from "@/types/api";

const SEVERITY_RANK: Record<string, number> = { critical: 0, warning: 1, info: 2 };

interface RowAction {
  label: string;
  Icon: ComponentType<{ size?: number; className?: string }>;
  loading?: boolean;
  run: () => void;
}

type ActionCtx = {
  gameName: string;
  toggle: ReturnType<typeof useToggleMod>;
  deploy: ReturnType<typeof useDeploy>;
  onGoToUpdates?: () => void;
};

/** Map an issue to the one-click fix it offers, or null if it's text-only. */
function resolveAction(issue: HealthIssueOut, ctx: ActionCtx): RowAction | null {
  switch (issue.kind) {
    case "missing_requirement":
      if (!issue.nexus_url) return null;
      return { label: "Get on Nexus", Icon: ExternalLink, run: () => void openUrl(issue.nexus_url!) };
    case "disabled_requirement":
      if (issue.action_mod_id == null) return null;
      return {
        label: "Enable",
        Icon: Power,
        loading: ctx.toggle.isPending && ctx.toggle.variables?.modId === issue.action_mod_id,
        run: () => ctx.toggle.mutate({ gameName: ctx.gameName, modId: issue.action_mod_id! }),
      };
    case "failed_install":
      return {
        label: "Re-deploy",
        Icon: RefreshCw,
        loading: ctx.deploy.isPending,
        run: () => ctx.deploy.mutate({ force: false }),
      };
    case "foreign_files":
      return {
        label: "Re-deploy",
        Icon: RefreshCw,
        loading: ctx.deploy.isPending,
        run: () => ctx.deploy.mutate({ force: true }),
      };
    case "outdated":
      return ctx.onGoToUpdates
        ? { label: "Update", Icon: ArrowUpCircle, run: ctx.onGoToUpdates }
        : null;
    default:
      return null; // misplaced_files, untracked_files: show the suggested-fix text
  }
}

function HealthRow({ issue, action }: { issue: HealthIssueOut; action: RowAction | null }) {
  const danger = issue.severity === "critical";
  const warning = issue.severity === "warning";
  const Icon = danger ? CircleAlert : warning ? AlertTriangle : Info;
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-lg border border-l-2 border-border bg-surface-2 px-3 py-2",
        danger ? "border-l-danger/70" : warning ? "border-l-warning/70" : "border-l-border",
      )}
    >
      <Icon
        size={14}
        className={cn(
          "mt-0.5 shrink-0",
          danger ? "text-danger" : warning ? "text-warning" : "text-text-muted",
        )}
      />
      <div className="min-w-0 flex-1 text-xs">
        <p className="text-text-secondary">
          {issue.mod_name && <span className="font-medium text-text-primary">{issue.mod_name}</span>}
          {issue.mod_name ? " " : ""}
          {issue.message}
        </p>
        {!action && issue.suggested_fix && <p className="text-text-muted">→ {issue.suggested_fix}</p>}
      </div>
      {action && (
        <Button
          size="sm"
          variant="secondary"
          loading={action.loading}
          onClick={action.run}
          className="shrink-0 self-center"
          title={issue.suggested_fix || action.label}
        >
          <action.Icon size={12} />
          {action.label}
        </Button>
      )}
    </div>
  );
}

/**
 * Pre-launch health check: requirement, install-integrity, misplaced-file and
 * foreign-file problems, each with the affected mod and — where possible — a
 * one-click fix (enable a dependency, re-deploy, open the Nexus page, jump to
 * Updates). Core-framework status is owned by the Frameworks panel and isn't
 * repeated here. Critical/warning issues surface up top; info-level ones fold
 * into a collapsed "Minor" section.
 */
export function HealthWidget({
  gameName,
  onGoToUpdates,
}: {
  gameName: string;
  onGoToUpdates?: () => void;
}) {
  const { data, isLoading, isError, refetch, isFetching } = useHealth(gameName);
  const toggle = useToggleMod();
  const deploy = useDeploy(gameName);
  const [showMinor, setShowMinor] = useState(false);

  if (isLoading) {
    return (
      <div className="rounded-xl border border-border bg-surface-1 p-4">
        <div className="h-4 w-36 animate-pulse rounded bg-surface-3" />
        <div className="mt-3 h-9 animate-pulse rounded-lg bg-surface-3" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-text-secondary">
        <CircleAlert size={16} className="shrink-0 text-danger" />
        Couldn&apos;t run the pre-launch check.
        <Button size="sm" variant="secondary" className="ml-auto" onClick={() => void refetch()}>
          <RotateCcw size={12} />
          Retry
        </Button>
      </div>
    );
  }

  if (data.issues.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-border bg-surface-1 px-4 py-3 text-sm text-text-secondary">
        <ShieldCheck size={16} className="shrink-0 text-success" />
        No issues found — your setup looks ready to launch.
      </div>
    );
  }

  const sorted = [...data.issues].sort(
    (a, b) => (SEVERITY_RANK[a.severity] ?? 9) - (SEVERITY_RANK[b.severity] ?? 9),
  );
  const needsAttention = sorted.filter((i) => i.severity !== "info");
  const minor = sorted.filter((i) => i.severity === "info");
  const ctx: ActionCtx = { gameName, toggle, deploy, onGoToUpdates };

  return (
    <div className="rounded-xl border border-border bg-surface-1 p-4">
      <div className="flex items-center gap-2">
        <HeartPulse size={16} className="shrink-0 text-accent" />
        <h3 className="text-sm font-semibold text-text-primary">Pre-launch check</h3>
        <span className="ml-auto flex items-center gap-1.5">
          {data.critical > 0 && <Badge variant="danger">{data.critical} critical</Badge>}
          {data.warning > 0 && <Badge variant="warning">{data.warning} warning</Badge>}
          {data.info > 0 && <Badge variant="neutral">{data.info} info</Badge>}
          <button
            type="button"
            onClick={() => void refetch()}
            title="Re-check now"
            className="ml-1 text-text-muted transition-colors hover:text-text-secondary"
          >
            <RotateCcw size={13} className={cn(isFetching && "animate-spin")} />
          </button>
        </span>
      </div>

      {needsAttention.length > 0 && (
        <div className="mt-3 space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Needs attention
          </p>
          {needsAttention.map((issue, i) => (
            <HealthRow key={i} issue={issue} action={resolveAction(issue, ctx)} />
          ))}
        </div>
      )}

      {minor.length > 0 && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowMinor((v) => !v)}
            className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-text-muted transition-colors hover:text-text-secondary"
          >
            <ChevronDown size={13} className={cn("transition-transform", showMinor && "rotate-180")} />
            Minor ({minor.length})
          </button>
          {showMinor && (
            <div className="mt-1.5 space-y-1.5">
              {minor.map((issue, i) => (
                <HealthRow key={i} issue={issue} action={resolveAction(issue, ctx)} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
