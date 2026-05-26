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
};

const isRequirement = (i: HealthIssueOut) =>
  i.kind === "missing_requirement" || i.kind === "disabled_requirement";

/** Action for a non-requirement issue (requirements get their own grouped UI). */
function resolveAction(issue: HealthIssueOut, ctx: ActionCtx): RowAction | null {
  switch (issue.kind) {
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

/** One card per requiring mod, listing each missing/disabled dependency with its fix. */
function RequirementGroup({
  modName,
  issues,
  ctx,
}: {
  modName: string;
  issues: HealthIssueOut[];
  ctx: ActionCtx;
}) {
  const danger = issues.some((i) => i.kind === "missing_requirement");
  const Icon = danger ? CircleAlert : AlertTriangle;
  return (
    <div
      className={cn(
        "rounded-lg border border-l-2 border-border bg-surface-2 px-3 py-2",
        danger ? "border-l-danger/70" : "border-l-warning/70",
      )}
    >
      <div className="flex items-center gap-2">
        <Icon size={14} className={cn("shrink-0", danger ? "text-danger" : "text-warning")} />
        <span className="text-sm font-medium text-text-primary">{modName}</span>
        <span className="text-xs text-text-muted">
          needs {issues.length} requirement{issues.length === 1 ? "" : "s"}
        </span>
      </div>
      <ul className="mt-1.5 space-y-1 pl-6">
        {issues.map((i, idx) => {
          const missing = i.kind === "missing_requirement";
          return (
            <li key={idx} className="flex items-center gap-2 text-xs">
              <span className="min-w-0 truncate text-text-secondary">
                {i.required_name || "A required mod"}
              </span>
              <Badge variant={missing ? "danger" : "warning"}>
                {missing ? "missing" : "disabled"}
              </Badge>
              <span className="ml-auto shrink-0">
                {missing && i.nexus_url && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => void openUrl(i.nexus_url!)}
                    title="Open the required mod's Nexus page"
                  >
                    <ExternalLink size={12} /> Get on Nexus
                  </Button>
                )}
                {!missing && i.action_mod_id != null && (
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={ctx.toggle.isPending && ctx.toggle.variables?.modId === i.action_mod_id}
                    onClick={() => ctx.toggle.mutate({ gameName: ctx.gameName, modId: i.action_mod_id! })}
                  >
                    <Power size={12} /> Enable
                  </Button>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * Pre-launch check: requirement, install-integrity, misplaced-file and
 * foreign-file problems, each with a one-click fix where possible. Missing/
 * disabled dependencies are grouped under the mod that needs them. Outdated
 * mods are the Updates tab's domain (a single pointer is shown, not a row each).
 * Core-framework status is owned by the Frameworks section below.
 */
export function HealthWidget({
  gameName,
  updatesCount = 0,
  onGoToUpdates,
}: {
  gameName: string;
  updatesCount?: number;
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

  const hasUpdates = updatesCount > 0 && !!onGoToUpdates;
  const updatesPointer = hasUpdates ? (
    <button
      type="button"
      onClick={onGoToUpdates}
      className="ml-auto flex items-center gap-1 text-xs text-text-muted transition-colors hover:text-text-secondary"
    >
      <ArrowUpCircle size={13} className="shrink-0" />
      {updatesCount} update{updatesCount === 1 ? "" : "s"} available →
    </button>
  ) : null;

  if (data.issues.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-surface-1 p-4">
        <div className="flex items-center gap-2 text-sm text-text-secondary">
          <ShieldCheck size={16} className="shrink-0 text-success" />
          No issues found, your setup looks ready to launch.
          {updatesPointer}
        </div>
      </div>
    );
  }

  const reqIssues = data.issues.filter(isRequirement);
  const otherAttention = data.issues.filter((i) => i.severity !== "info" && !isRequirement(i));
  const minor = data.issues.filter((i) => i.severity === "info");

  // Group requirement issues under the mod that needs them; critical (missing) first.
  const groups = new Map<string, HealthIssueOut[]>();
  for (const i of reqIssues) {
    const key = i.mod_name || "Unknown mod";
    (groups.get(key) ?? groups.set(key, []).get(key)!).push(i);
  }
  const reqGroups = [...groups.entries()]
    .map(([modName, issues]) => ({ modName, issues }))
    .sort(
      (a, b) =>
        Number(b.issues.some((i) => i.kind === "missing_requirement")) -
        Number(a.issues.some((i) => i.kind === "missing_requirement")),
    );

  const ctx: ActionCtx = { gameName, toggle, deploy };
  const hasAttention = reqGroups.length > 0 || otherAttention.length > 0;

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

      {hasAttention && (
        <div className="mt-3 space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Needs attention
          </p>
          {reqGroups.map((g) => (
            <RequirementGroup key={g.modName} modName={g.modName} issues={g.issues} ctx={ctx} />
          ))}
          {otherAttention.map((issue, i) => (
            <HealthRow key={i} issue={issue} action={resolveAction(issue, ctx)} />
          ))}
        </div>
      )}

      {(minor.length > 0 || updatesPointer) && (
        <div className="mt-3">
          <div className="flex items-center gap-3">
            {minor.length > 0 ? (
              <button
                type="button"
                onClick={() => setShowMinor((v) => !v)}
                className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-text-muted transition-colors hover:text-text-secondary"
              >
                <ChevronDown
                  size={13}
                  className={cn("transition-transform", showMinor && "rotate-180")}
                />
                Minor ({minor.length})
              </button>
            ) : null}
            {updatesPointer}
          </div>
          {minor.length > 0 && showMinor && (
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
