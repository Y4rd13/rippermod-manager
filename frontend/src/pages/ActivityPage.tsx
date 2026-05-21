import { History } from "lucide-react";

import { Card } from "@/components/ui/Card";
import { useActivity, useGames } from "@/hooks/queries";
import { isoToEpoch, timeAgo } from "@/lib/format";

const ACTION_LABELS: Record<string, string> = {
  install: "Installed",
  uninstall: "Uninstalled",
  enable: "Enabled",
  disable: "Disabled",
  deploy: "Deployed",
  undeploy: "Undeployed",
  download: "Downloaded",
};

function GameActivity({ gameName }: { gameName: string }) {
  const { data: entries = [], isLoading } = useActivity(gameName);

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
            <th className="py-1.5 font-medium">When</th>
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
                {e.target || "—"}
              </td>
              <td className="py-1.5 pr-3 text-text-muted">{e.detail || "—"}</td>
              <td
                className="whitespace-nowrap py-1.5 text-text-muted"
                title={e.created_at}
              >
                {timeAgo(isoToEpoch(e.created_at))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
