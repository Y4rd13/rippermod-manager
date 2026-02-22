import { CheckCircle, FolderOpen, Gamepad2, Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "@/stores/toast-store";
import { Link } from "react-router";
import { open } from "@tauri-apps/plugin-dialog";
import { invoke } from "@tauri-apps/api/core";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { useCreateGame, useDeleteGame, useValidatePath } from "@/hooks/mutations";
import { useGames } from "@/hooks/queries";
import type { DetectedGame, PathValidation } from "@/types/api";

function AddGameDialog({
  open: isOpen,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [name, setName] = useState("Cyberpunk 2077");
  const [installPath, setInstallPath] = useState("");
  const [error, setError] = useState("");
  const [detectedPaths, setDetectedPaths] = useState<DetectedGame[]>([]);
  const [isDetecting, setIsDetecting] = useState(false);
  const [validation, setValidation] = useState<PathValidation | null>(null);
  const createGame = useCreateGame();
  const validatePath = useValidatePath();

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleValidate = (path: string) => {
    validatePath.mutate(
      { install_path: path, domain_name: "cyberpunk2077" },
      {
        onSuccess: (result) => setValidation(result),
        onError: () => setValidation(null),
      },
    );
  };

  const handleAutoDetect = async () => {
    setIsDetecting(true);
    setError("");
    setDetectedPaths([]);
    setValidation(null);
    try {
      const paths = await invoke<DetectedGame[]>("detect_game_paths");
      if (paths.length === 1) {
        setInstallPath(paths[0].path);
        handleValidate(paths[0].path);
      } else if (paths.length > 1) {
        setDetectedPaths(paths);
      } else {
        setError("No installations found. Use Browse to select your game folder.");
      }
    } catch {
      setError("Auto-detection failed. Use Browse to select your game folder.");
    } finally {
      setIsDetecting(false);
    }
  };

  const handleSelectDetected = (path: string) => {
    setInstallPath(path);
    setDetectedPaths([]);
    handleValidate(path);
  };

  const handleBrowse = async () => {
    const selected = await open({
      directory: true,
      title: "Select game installation folder",
      defaultPath: installPath || undefined,
    });
    if (selected) {
      setInstallPath(selected);
      setDetectedPaths([]);
      setError("");
      handleValidate(selected);
    }
  };

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
          setValidation(null);
          setDetectedPaths([]);
          setError("");
        },
        onError: (e) => toast.error("Failed to add game", e.message),
      },
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" role="dialog" aria-modal="true">
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

          <div className="space-y-2">
            <label className="block text-sm font-medium text-text-secondary">
              Installation Path
            </label>
            <div className="flex items-center gap-2">
              <div className="flex-1 rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm truncate">
                {installPath ? (
                  <span className="text-text-primary">{installPath}</span>
                ) : (
                  <span className="text-text-muted">Auto-detect or browse for your game folder</span>
                )}
              </div>
              <Button
                variant="ghost"
                size="sm"
                disabled={isDetecting}
                onClick={handleAutoDetect}
                loading={isDetecting}
              >
                <Search className="h-4 w-4 mr-1" />
                Auto-detect
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleBrowse}
              >
                <FolderOpen className="h-4 w-4 mr-1" />
                Browse
              </Button>
            </div>

            {detectedPaths.length > 1 && (
              <div className="rounded-lg border border-border bg-surface-1 p-2 space-y-1">
                <p className="text-xs text-text-muted px-1 mb-1">
                  Multiple installations found. Select one:
                </p>
                {detectedPaths.map((d) => (
                  <button
                    key={d.path}
                    type="button"
                    onClick={() => handleSelectDetected(d.path)}
                    className="flex w-full items-center justify-between rounded-md px-3 py-2 text-sm hover:bg-surface-2 transition-colors"
                  >
                    <span className="text-text-primary truncate">{d.path}</span>
                    <span className="shrink-0 ml-2 text-xs text-accent font-medium">
                      {d.source}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {validation && (
              <div className="flex items-center gap-2 text-xs">
                {validation.valid ? (
                  <>
                    <CheckCircle className="h-3.5 w-3.5 text-success" />
                    <span className="text-success">
                      Valid installation ({validation.found_mod_dirs.length} mod directories found)
                    </span>
                  </>
                ) : (
                  <span className="text-danger">{validation.warning}</span>
                )}
              </div>
            )}

            {error && <p className="text-danger text-sm">{error}</p>}
          </div>

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
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

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
                {confirmDelete === game.name ? (
                  <Button
                    variant="danger"
                    size="sm"
                    loading={
                      deleteGame.isPending &&
                      deleteGame.variables === game.name
                    }
                    onClick={() => {
                      deleteGame.mutate(game.name);
                      setConfirmDelete(null);
                    }}
                  >
                    Confirm
                  </Button>
                ) : (
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => setConfirmDelete(game.name)}
                  >
                    <Trash2 size={14} />
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      <AddGameDialog open={showAdd} onClose={() => setShowAdd(false)} />
    </div>
  );
}
