import { History, Undo2 } from "lucide-react";
import { useState } from "react";

import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useUndoActivity } from "@/hooks/mutations";
import { useActivity, useGames } from "@/hooks/queries";
import { isoToEpoch, timeAgo } from "@/lib/format";
import type { ActivityLogEntry } from "@/types/api";

const ACTION_LABELS: Record<string, string> = {
  install: "Installed",
  uninstall: "Uninstalled",
  enable: "Enabled",
  disable: "Disabled",
  deploy: "Deployed",
  undeploy: "Undeployed",
  download: "Downloaded",
  undo: "Undid",
};

// Actions whose inverse is implemented (Tier A+B). Others are observe-only.
const UNDOABLE_ACTIONS = new Set(["install", "uninstall", "enable", "disable"]);

function undoMessage(e: ActivityLogEntry): string {
  switch (e.action) {
    case "install":
      return `Undo installing "${e.target}"? This uninstalls the mod and removes its files from the game.`;
    case "uninstall":
      return `Undo uninstalling "${e.target}"? This reinstalls it from the original archive, but its prior load order and enabled state aren't restored.`;
    case "enable":
      return `Undo enabling "${e.target}"? This disables it again.`;
    case "disable":
      return `Undo disabling "${e.target}"? This re-enables it.`;
    default:
      return "Undo this action?";
  }
}

function GameActivity({ gameName }: { gameName: string }) {
  const { data: entries = [], isLoading } = useActivity(gameName);
  const undoActivity = useUndoActivity();
  const [confirmUndo, setConfirmUndo] = useState<ActivityLogEntry | null>(null);

  if (isLoading) {
    return <p className="py-4 text-sm text-text-muted">Loading…</p>;
  }
  if (entries.length === 0) {
    return <p className="py-4 text-sm text-text-muted">No activity recorded yet.</p>;
  }

  return (
    <div className="max-h-96 overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface-1">
          <tr className="text-left text-xs text-text-muted">
            <th className="py-1.5 pr-3 font-medium">Action</th>
            <th className="py-1.5 pr-3 font-medium">Mod</th>
            <th className="py-1.5 pr-3 font-medium">Details</th>
            <th className="py-1.5 pr-3 font-medium">When</th>
            <th className="py-1.5 font-medium" />
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id} className="border-t border-border">
              <td className="py-1.5 pr-3">
                <span className="inline-block rounded bg-surface-2 px-1.5 py-0.5 text-xs font-medium text-text-secondary">
                  {ACTION_LABELS[e.action] ?? e.action}
                </span>
              </td>
              <td className="max-w-xs truncate py-1.5 pr-3 text-text-secondary">
                {e.target || "-"}
              </td>
              <td className="py-1.5 pr-3 text-text-muted">{e.detail || "-"}</td>
              <td className="whitespace-nowrap py-1.5 pr-3 text-text-muted" title={e.created_at}>
                {timeAgo(isoToEpoch(e.created_at))}
              </td>
              <td className="whitespace-nowrap py-1.5 text-right">
                {e.undone_at ? (
                  <span className="text-xs text-text-muted">Undone</span>
                ) : e.undoable && UNDOABLE_ACTIONS.has(e.action) ? (
                  <button
                    type="button"
                    onClick={() => setConfirmUndo(e)}
                    disabled={undoActivity.isPending}
                    className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-text-muted transition-colors hover:bg-surface-2 hover:text-text-secondary disabled:opacity-50"
                  >
                    <Undo2 size={12} /> Undo
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {confirmUndo && (
        <ConfirmDialog
          title="Undo action?"
          message={undoMessage(confirmUndo)}
          confirmLabel="Undo"
          variant="warning"
          icon={Undo2}
          loading={undoActivity.isPending}
          onConfirm={() =>
            undoActivity.mutate(
              { gameName, entryId: confirmUndo.id },
              { onSuccess: () => setConfirmUndo(null), onError: () => setConfirmUndo(null) },
            )
          }
          onCancel={() => setConfirmUndo(null)}
        />
      )}
    </div>
  );
}

export function ActivityPage() {
  const { data: games = [] } = useGames();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <History size={24} className="text-accent" />
        <h1 className="text-2xl font-bold text-text-primary">Activity</h1>
      </div>

      {games.length === 0 ? (
        <Card>
          <p className="py-8 text-center text-sm text-text-muted">
            Add a game to see its activity history.
          </p>
        </Card>
      ) : (
        games.map((game) => (
          <Card key={game.id}>
            <h2 className="mb-4 text-lg font-semibold text-text-primary">{game.name}</h2>
            <GameActivity gameName={game.name} />
          </Card>
        ))
      )}
    </div>
  );
}
