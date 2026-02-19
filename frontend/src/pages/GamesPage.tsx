import { Gamepad2, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { useCreateGame, useDeleteGame } from "@/hooks/mutations";
import { useGames } from "@/hooks/queries";

function AddGameDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [name, setName] = useState("Cyberpunk 2077");
  const [installPath, setInstallPath] = useState("");
  const [error, setError] = useState("");
  const createGame = useCreateGame();

  if (!open) return null;

  const handleCreate = () => {
    if (!installPath.trim()) {
      setError("Install path required");
      return;
    }
    createGame.mutate(
      { name, domain_name: "cyberpunk2077", install_path: installPath },
      {
        onSuccess: () => {
          onClose();
          setName("Cyberpunk 2077");
          setInstallPath("");
        },
        onError: (e) => setError(e.message),
      },
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <Card className="w-full max-w-md">
        <h2 className="text-lg font-semibold text-text-primary mb-4">
          Add Game
        </h2>
        <div className="space-y-4">
          <Input
            id="game-name"
            label="Game Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Input
            id="install-path"
            label="Install Path"
            placeholder="C:\\...\\Cyberpunk 2077"
            value={installPath}
            onChange={(e) => {
              setInstallPath(e.target.value);
              setError("");
            }}
            error={error}
          />
          <div className="flex justify-end gap-3">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={handleCreate} loading={createGame.isPending}>
              Add Game
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

export function GamesPage() {
  const { data: games = [] } = useGames();
  const deleteGame = useDeleteGame();
  const [showAdd, setShowAdd] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-text-primary">Games</h1>
        <Button onClick={() => setShowAdd(true)} size="sm">
          <Plus size={16} /> Add Game
        </Button>
      </div>

      {games.length === 0 ? (
        <Card>
          <p className="text-text-muted text-center py-8">
            No games configured. Add one to get started.
          </p>
        </Card>
      ) : (
        <div className="grid gap-4">
          {games.map((game) => (
            <Card key={game.id}>
              <div className="flex items-center justify-between">
                <Link
                  to={`/games/${game.name}`}
                  className="flex items-center gap-3 hover:text-accent transition-colors"
                >
                  <Gamepad2 size={20} className="text-accent" />
                  <div>
                    <p className="font-semibold text-text-primary">
                      {game.name}
                    </p>
                    <p className="text-xs text-text-muted">{game.install_path}</p>
                    <p className="text-xs text-text-muted mt-1">
                      {game.mod_paths.length} mod directories configured
                    </p>
                  </div>
                </Link>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => deleteGame.mutate(game.name)}
                  loading={deleteGame.isPending}
                >
                  <Trash2 size={14} />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <AddGameDialog open={showAdd} onClose={() => setShowAdd(false)} />
    </div>
  );
}
