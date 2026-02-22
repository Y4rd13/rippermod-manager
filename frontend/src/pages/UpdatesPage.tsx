import { RefreshCw } from "lucide-react";

import { UpdatesTable } from "@/components/mods/UpdatesTable";
import { Card } from "@/components/ui/Card";
import { useGames, useUpdates } from "@/hooks/queries";

function GameUpdates({ gameName }: { gameName: string }) {
  const { data: updates, isLoading } = useUpdates(gameName);

  return (
    <UpdatesTable
      gameName={gameName}
      updates={updates?.updates ?? []}
      isLoading={isLoading}
    />
  );
}

export function UpdatesPage() {
  const { data: games = [] } = useGames();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <RefreshCw size={24} className="text-accent" />
        <h1 className="text-2xl font-bold text-text-primary">Updates</h1>
      </div>

      {games.length === 0 ? (
        <Card>
          <p className="text-text-muted text-sm text-center py-8">
            Add a game first to check for updates.
          </p>
        </Card>
      ) : (
        games.map((game) => (
          <Card key={game.id}>
            <h2 className="text-lg font-semibold text-text-primary mb-4">
              {game.name}
            </h2>
            <GameUpdates gameName={game.name} />
          </Card>
        ))
      )}
    </div>
  );
}
