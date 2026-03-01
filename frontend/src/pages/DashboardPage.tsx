import { AlertTriangle, Download, Gamepad2, Heart, Link2, Package, RefreshCw, Scan, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";

import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import { useConflictsOverview, useGames, useInstalledMods, useMods, useTrendingMods, useUpdates } from "@/hooks/queries";
import { formatCount } from "@/lib/format";
import type { TrendingMod } from "@/types/api";

interface GameStatsData {
  totalInstalled: number;
  nexusMatched: number;
  updatesAvailable: number;
  conflictsAffected: number;
}

function StatCard({
  icon: Icon,
  label,
  value,
  color,
  hoverBorder,
  onClick,
  title,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  color: string;
  hoverBorder?: string;
  onClick?: () => void;
  title?: string;
}) {
  return (
    <Card
      className={cn(hoverBorder && `${hoverBorder} transition-colors`)}
      onClick={onClick}
      title={title}
    >
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

function GameStatsReporter({ gameName, onReport }: { gameName: string; onReport: (name: string, stats: GameStatsData) => void }) {
  const { data: mods = [] } = useMods(gameName);
  const { data: installed = [] } = useInstalledMods(gameName);
  const { data: updates } = useUpdates(gameName);
  const { data: conflicts } = useConflictsOverview(gameName);

  const stats = useMemo(() => ({
    totalInstalled: installed.length,
    nexusMatched: mods.filter((m) => m.nexus_match).length,
    updatesAvailable: updates?.updates_available ?? 0,
    conflictsAffected: conflicts?.mods_affected ?? 0,
  }), [installed.length, mods, updates?.updates_available, conflicts?.mods_affected]);

  const serialized = `${stats.totalInstalled}-${stats.nexusMatched}-${stats.updatesAvailable}-${stats.conflictsAffected}`;
  const lastRef = useRef("");

  useEffect(() => {
    if (lastRef.current !== serialized) {
      lastRef.current = serialized;
      onReport(gameName, stats);
    }
  }, [serialized, gameName, stats, onReport]);

  return null;
}

const PLACEHOLDER_IMG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48' fill='%231a1a2e'%3E%3Crect width='48' height='48'/%3E%3C/svg%3E";

function TrendingMiniCard({ mod }: { mod: TrendingMod }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border p-2 hover:bg-surface-2 transition-colors">
      <img
        src={mod.picture_url || PLACEHOLDER_IMG}
        alt={mod.name}
        loading="lazy"
        className="w-12 h-12 rounded-md object-cover bg-surface-2 shrink-0"
        onError={(e) => {
          (e.target as HTMLImageElement).src = PLACEHOLDER_IMG;
        }}
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-text-primary truncate">
          {mod.name}
        </p>
        <p className="text-xs text-text-muted truncate">{mod.author}</p>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="inline-flex items-center gap-0.5 text-xs text-text-muted">
            <Download size={10} />
            {formatCount(mod.mod_downloads)}
          </span>
          {mod.endorsement_count > 0 && (
            <span className="inline-flex items-center gap-0.5 text-xs text-text-muted">
              <Heart size={10} />
              {formatCount(mod.endorsement_count)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function CommunityActivity({ gameName }: { gameName: string }) {
  const { data: trending } = useTrendingMods(gameName);
  const mods = trending?.trending ?? [];

  if (mods.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <TrendingUp size={14} className="text-accent" />
        <h3 className="text-sm font-medium text-text-secondary">{gameName}</h3>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {mods.map((mod) => (
          <Link key={mod.mod_id} to={`/games/${gameName}`}>
            <TrendingMiniCard mod={mod} />
          </Link>
        ))}
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { data: games = [] } = useGames();
  const [gameStats, setGameStats] = useState<Record<string, GameStatsData>>({});
  const navigate = useNavigate();

  const handleReport = useCallback((name: string, stats: GameStatsData) => {
    setGameStats((prev) => ({ ...prev, [name]: stats }));
  }, []);

  const totals = useMemo(() => {
    let totalInstalled = 0;
    let nexusMatched = 0;
    let updatesAvailable = 0;
    let conflictsAffected = 0;
    for (const s of Object.values(gameStats)) {
      totalInstalled += s.totalInstalled;
      nexusMatched += s.nexusMatched;
      updatesAvailable += s.updatesAvailable;
      conflictsAffected += s.conflictsAffected;
    }
    return { totalInstalled, nexusMatched, updatesAvailable, conflictsAffected };
  }, [gameStats]);

  const firstGame = games[0]?.name;

  const gamesWithUpdates = useMemo(() => {
    return Object.entries(gameStats)
      .filter(([, s]) => s.updatesAvailable > 0)
      .map(([name, s]) => ({ name, count: s.updatesAvailable }));
  }, [gameStats]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>

      {games.map((game) => (
        <GameStatsReporter key={game.id} gameName={game.name} onReport={handleReport} />
      ))}

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <StatCard
          icon={Gamepad2}
          label="Games"
          value={games.length}
          color="bg-accent/10 text-accent"
          hoverBorder="hover:border-accent/40"
          onClick={firstGame ? () => navigate(`/games/${firstGame}`) : undefined}
          title="View your games"
        />
        <StatCard
          icon={Package}
          label="Total Mods"
          value={games.length > 0 ? totals.totalInstalled : "--"}
          color="bg-success/10 text-success"
          hoverBorder="hover:border-success/40"
          onClick={firstGame ? () => navigate(`/games/${firstGame}`) : undefined}
          title="View installed mods"
        />
        <StatCard
          icon={Link2}
          label="Nexus Matched"
          value={games.length > 0 ? totals.nexusMatched : "--"}
          color="bg-warning/10 text-warning"
          hoverBorder="hover:border-warning/40"
          onClick={firstGame ? () => navigate(`/games/${firstGame}`) : undefined}
          title="View Nexus matched mods"
        />
        <StatCard
          icon={RefreshCw}
          label="Updates Available"
          value={games.length > 0 ? totals.updatesAvailable : "--"}
          color="bg-danger/10 text-danger"
          hoverBorder="hover:border-danger/40"
          onClick={firstGame ? () => navigate(`/games/${firstGame}`) : undefined}
          title="View available updates"
        />
        <StatCard
          icon={AlertTriangle}
          label="Conflicts"
          value={games.length > 0 ? totals.conflictsAffected : "--"}
          color={totals.conflictsAffected > 0 ? "bg-warning/10 text-warning" : "bg-success/10 text-success"}
          hoverBorder={totals.conflictsAffected > 0 ? "hover:border-warning/40" : "hover:border-success/40"}
          onClick={firstGame ? () => navigate(`/games/${firstGame}`) : undefined}
          title="Mods with file or resource conflicts"
        />
      </div>

      {gamesWithUpdates.length > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-warning/30 bg-warning/5 px-4 py-3">
          <AlertTriangle size={18} className="text-warning shrink-0" />
          <p className="text-sm text-text-secondary flex-1">
            Updates available:{" "}
            {gamesWithUpdates.map((g, i) => (
              <span key={g.name}>
                {i > 0 && ", "}
                <Link to={`/games/${g.name}`} className="font-medium text-warning hover:underline">
                  {g.name}
                </Link>
                {" "}({g.count})
              </span>
            ))}
          </p>
        </div>
      )}

      {games.length > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-text-secondary">Quick Actions</span>
          <Link
            to={`/games/${firstGame}`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-1 px-3 py-1.5 text-sm text-text-secondary hover:bg-surface-2 hover:text-text-primary transition-colors"
          >
            <Scan size={14} />
            Go to Scan & Correlate
          </Link>
          {totals.updatesAvailable > 0 && (
            <Link
              to={`/games/${firstGame}`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-1 px-3 py-1.5 text-sm text-text-secondary hover:bg-surface-2 hover:text-text-primary transition-colors"
            >
              <RefreshCw size={14} />
              Go to Updates
            </Link>
          )}
        </div>
      )}

      <Card>
        <h2 className="text-lg font-semibold text-text-primary mb-4">
          Your Games
        </h2>
        {games.length === 0 ? (
          <p className="text-text-muted text-sm">No games configured yet.</p>
        ) : (
          <div className="space-y-2">
            {games.map((game) => {
              const stats = gameStats[game.name];
              return (
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
                  <div className="flex items-center gap-3">
                    {stats && stats.updatesAvailable > 0 && (
                      <span className="inline-flex items-center gap-1 text-xs text-warning">
                        <RefreshCw size={12} />
                        {stats.updatesAvailable}
                      </span>
                    )}
                    <span className="text-xs text-text-muted">
                      {stats ? `${stats.totalInstalled} mods` : `${game.mod_paths.length} mod paths`}
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </Card>

      {games.length > 0 && (
        <Card>
          <h2 className="text-lg font-semibold text-text-primary mb-4">
            Community Activity
          </h2>
          <div className="space-y-4">
            {games.map((game) => (
              <CommunityActivity key={game.id} gameName={game.name} />
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
