import { Download, RefreshCw, Search } from "lucide-react";

import { SourceBadge } from "@/components/mods/SourceBadge";
import { UpdateDownloadCell } from "@/components/mods/UpdateDownloadCell";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useCheckUpdates, useStartDownload } from "@/hooks/mutations";
import { useDownloadJobs, useGames, useUpdates } from "@/hooks/queries";

function GameUpdates({ gameName }: { gameName: string }) {
  const { data: updates, isLoading } = useUpdates(gameName);
  const { data: downloadJobs = [] } = useDownloadJobs(gameName);
  const checkUpdates = useCheckUpdates();
  const startDownload = useStartDownload();

  if (isLoading) {
    return <p className="text-text-muted text-sm">Checking {gameName}...</p>;
  }

  const downloadableUpdates = (updates?.updates ?? []).filter(
    (u) => u.nexus_file_id != null,
  );

  const handleUpdateAll = async () => {
    for (const u of downloadableUpdates) {
      if (u.nexus_file_id) {
        try {
          await startDownload.mutateAsync({
            gameName,
            data: {
              nexus_mod_id: u.nexus_mod_id,
              nexus_file_id: u.nexus_file_id,
            },
          });
        } catch {
          // Individual download errors handled by mutation callbacks
        }
      }
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-text-muted text-xs">
          {updates?.updates_available ?? 0} update(s) available
        </p>
        <div className="flex items-center gap-2">
          {downloadableUpdates.length > 1 && (
            <Button
              variant="secondary"
              size="sm"
              onClick={handleUpdateAll}
              loading={startDownload.isPending}
            >
              <Download className="h-3.5 w-3.5 mr-1" />
              Update All ({downloadableUpdates.length})
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => checkUpdates.mutate(gameName)}
            loading={checkUpdates.isPending}
          >
            <Search className="h-3.5 w-3.5 mr-1" />
            Check Now
          </Button>
        </div>
      </div>

      {!updates?.updates.length ? (
        <p className="text-text-muted text-sm">
          No updates available for {gameName}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text-muted">
                <th className="pb-2 pr-4">Mod</th>
                <th className="pb-2 pr-4">Local</th>
                <th className="pb-2 pr-4">Available</th>
                <th className="pb-2 pr-4">Source</th>
                <th className="pb-2 pr-4">Author</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody>
              {updates.updates.map((u, i) => (
                <tr
                  key={u.installed_mod_id ?? `group-${u.mod_group_id ?? i}`}
                  className="border-b border-border/50"
                >
                  <td className="py-2 pr-4 text-text-primary font-medium">
                    {u.display_name}
                  </td>
                  <td className="py-2 pr-4 text-text-muted">
                    {u.local_version}
                  </td>
                  <td className="py-2 pr-4 text-success font-medium">
                    {u.nexus_version}
                  </td>
                  <td className="py-2 pr-4">
                    <SourceBadge source={u.source} />
                  </td>
                  <td className="py-2 pr-4 text-text-muted">{u.author}</td>
                  <td className="py-2">
                    <UpdateDownloadCell
                      update={u}
                      gameName={gameName}
                      downloadJobs={downloadJobs}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
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
