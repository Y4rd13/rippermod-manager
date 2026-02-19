import { Gamepad2, Package, RefreshCw, Link2 } from "lucide-react";
import { Link } from "react-router";

import { Card } from "@/components/ui/Card";
import { useGames } from "@/hooks/queries";

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  color: string;
}) {
  return (
    <Card>
      <div className="flex items-center gap-4">
        <div className={`rounded-lg p-2.5 ${color}`}>
          <Icon size={20} />
        </div>
        <div>
          <p className="text-sm text-text-secondary">{label}</p>
          <p className="text-2xl font-bold text-text-primary">{value}</p>
        </div>
      </div>
    </Card>
  );
}

export function DashboardPage() {
  const { data: games = [] } = useGames();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Gamepad2}
          label="Games"
          value={games.length}
          color="bg-accent/10 text-accent"
        />
        <StatCard
          icon={Package}
          label="Total Mods"
          value="--"
          color="bg-success/10 text-success"
        />
        <StatCard
          icon={Link2}
          label="Nexus Matched"
          value="--"
          color="bg-warning/10 text-warning"
        />
        <StatCard
          icon={RefreshCw}
          label="Updates Available"
          value="--"
          color="bg-danger/10 text-danger"
        />
      </div>

      <Card>
        <h2 className="text-lg font-semibold text-text-primary mb-4">
          Your Games
        </h2>
        {games.length === 0 ? (
          <p className="text-text-muted text-sm">No games configured yet.</p>
        ) : (
          <div className="space-y-2">
            {games.map((game) => (
              <Link
                key={game.id}
                to={`/games/${game.name}`}
                className="flex items-center justify-between rounded-lg border border-border p-3 hover:bg-surface-2 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <Gamepad2 size={18} className="text-accent" />
                  <div>
                    <p className="text-sm font-medium text-text-primary">
                      {game.name}
                    </p>
                    <p className="text-xs text-text-muted">{game.install_path}</p>
                  </div>
                </div>
                <span className="text-xs text-text-muted">
                  {game.mod_paths.length} mod paths
                </span>
              </Link>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
