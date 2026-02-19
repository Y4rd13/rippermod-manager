import {
  Archive,
  Download,
  FolderOpen,
  Link2,
  Package,
  Play,
  RefreshCw,
  Scan,
  UserCheck,
} from "lucide-react";
import { invoke } from "@tauri-apps/api/core";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router";

import { ArchivesList } from "@/components/mods/ArchivesList";
import { InstalledModsTable } from "@/components/mods/InstalledModsTable";
import { ModsTable } from "@/components/mods/ModsTable";
import { ProfileManager } from "@/components/mods/ProfileManager";
import { UpdateDownloadCell } from "@/components/mods/UpdateDownloadCell";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ScanProgress, type ScanLog } from "@/components/ui/ScanProgress";
import { useCheckUpdates, useCorrelate, useStartDownload, useSyncNexus } from "@/hooks/mutations";
import {
  useAvailableArchives,
  useDownloadJobs,
  useGame,
  useGameVersion,
  useInstalledMods,
  useMods,
  useProfiles,
  useUpdates,
} from "@/hooks/queries";
import { api } from "@/lib/api-client";
import { parseSSE } from "@/lib/sse-parser";
import { cn } from "@/lib/utils";
import { toast } from "@/stores/toast-store";
import type { ModUpdate } from "@/types/api";

type Tab = "mods" | "installed" | "archives" | "profiles" | "updates";

const TABS: { key: Tab; label: string; Icon: typeof Package }[] = [
  { key: "mods", label: "Scanned", Icon: Package },
  { key: "installed", label: "Installed", Icon: UserCheck },
  { key: "archives", label: "Archives", Icon: Archive },
  { key: "profiles", label: "Profiles", Icon: FolderOpen },
  { key: "updates", label: "Updates", Icon: RefreshCw },
];

function UpdatesTab({ gameName, updates }: { gameName: string; updates: ModUpdate[] }) {
  const { data: downloadJobs = [] } = useDownloadJobs(gameName);
  const checkUpdates = useCheckUpdates();
  const startDownload = useStartDownload();

  const downloadableUpdates = updates.filter((u) => u.nexus_file_id != null);

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
          {updates.length} update(s) available
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
            <RefreshCw className="h-3.5 w-3.5 mr-1" />
            Check Now
          </Button>
        </div>
      </div>

      {!updates.length ? (
        <p className="text-text-muted text-sm py-4">No updates detected. Run a scan first.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text-muted">
                <th className="pb-2 pr-4">Mod</th>
                <th className="pb-2 pr-4">Local Version</th>
                <th className="pb-2 pr-4">Nexus Version</th>
                <th className="pb-2 pr-4">Author</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody>
              {updates.map((u, i) => (
                <tr
                  key={u.installed_mod_id ?? `group-${u.mod_group_id ?? i}`}
                  className="border-b border-border/50"
                >
                  <td className="py-2 pr-4 text-text-primary">{u.display_name}</td>
                  <td className="py-2 pr-4 text-text-muted">{u.local_version}</td>
                  <td className="py-2 pr-4 text-success font-medium">{u.nexus_version}</td>
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

export function GameDetailPage() {
  const { name = "" } = useParams();
  const { data: game } = useGame(name);
  const { data: gameVersion } = useGameVersion(name);
  const { data: mods = [] } = useMods(name);
  const { data: installedMods = [] } = useInstalledMods(name);
  const { data: archives = [] } = useAvailableArchives(name);
  const { data: profiles = [] } = useProfiles(name);
  const { data: updates } = useUpdates(name);
  const queryClient = useQueryClient();
  const syncNexus = useSyncNexus();
  const correlate = useCorrelate();
  const [tab, setTab] = useState<Tab>("mods");

  const [isLaunching, setIsLaunching] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [scanLogs, setScanLogs] = useState<ScanLog[]>([]);
  const [scanPercent, setScanPercent] = useState(0);
  const [scanPhase, setScanPhase] = useState("");

  const pendingLogs = useRef<ScanLog[]>([]);
  const latestPercent = useRef(0);
  const latestPhase = useRef("");
  const flushTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);

  const startFlushing = useCallback(() => {
    flushTimer.current = setInterval(() => {
      if (pendingLogs.current.length > 0) {
        const batch = pendingLogs.current;
        pendingLogs.current = [];
        setScanLogs((prev) => [...prev, ...batch]);
      }
      setScanPercent(latestPercent.current);
      setScanPhase(latestPhase.current);
    }, 150);
  }, []);

  const stopFlushing = useCallback(() => {
    if (flushTimer.current) clearInterval(flushTimer.current);
    if (pendingLogs.current.length > 0) {
      const batch = pendingLogs.current;
      pendingLogs.current = [];
      setScanLogs((prev) => [...prev, ...batch]);
    }
    setScanPercent(latestPercent.current);
    setScanPhase(latestPhase.current);
  }, []);

  const pushLog = useCallback((log: ScanLog) => {
    pendingLogs.current.push(log);
    if (log.percent >= 0) latestPercent.current = log.percent;
    latestPhase.current = log.phase;
  }, []);

  useEffect(() => {
    return () => {
      if (flushTimer.current) clearInterval(flushTimer.current);
      abortRef.current?.abort();
    };
  }, []);

  const handleLaunch = async () => {
    if (!game || !gameVersion?.exe_path) return;
    setIsLaunching(true);
    try {
      await invoke<void>("launch_game", {
        installPath: game.install_path,
        exeRelativePath: gameVersion.exe_path,
        launchArgs: ["--launcher-skip"],
      });
      toast.success("Game launched");
    } catch (e) {
      const msg = typeof e === "string" ? e : "Launch failed";
      toast.error("Launch failed", msg);
    } finally {
      setIsLaunching(false);
    }
  };

  const handleFullScan = async () => {
    setIsScanning(true);
    setScanLogs([]);
    setScanPercent(0);
    setScanPhase("scan");
    pendingLogs.current = [];
    latestPercent.current = 0;
    latestPhase.current = "scan";

    try {
      pushLog({ phase: "scan", message: "Starting mod scan...", percent: 0 });
      startFlushing();

      const controller = new AbortController();
      abortRef.current = controller;
      const response = await api.stream(
        `/api/v1/games/${name}/mods/scan-stream`,
        undefined,
        controller.signal,
      );

      for await (const event of parseSSE(response)) {
        const data = JSON.parse(event.data) as ScanLog;
        pushLog(data);
      }

      pushLog({ phase: "sync", message: "Syncing Nexus history...", percent: 100 });
      latestPhase.current = "sync";
      latestPercent.current = 100;

      try {
        await syncNexus.mutateAsync(name);
        pushLog({ phase: "sync", message: "Nexus sync complete", percent: 100 });
      } catch {
        pushLog({ phase: "sync", message: "Nexus sync skipped (optional)", percent: 100 });
      }

      pushLog({ phase: "correlate", message: "Correlating mods...", percent: 100 });
      latestPhase.current = "correlate";

      const corrResult = await correlate.mutateAsync(name);
      pushLog({
        phase: "done",
        message: `Done: ${corrResult.matched} matched, ${corrResult.unmatched} unmatched`,
        percent: 100,
      });
      latestPhase.current = "done";

      stopFlushing();
      setScanPhase("done");
      setScanPercent(100);
      queryClient.invalidateQueries({ queryKey: ["mods", name] });
      queryClient.invalidateQueries({ queryKey: ["installed-mods", name] });
      toast.success("Scan complete", `${corrResult.matched} matched, ${corrResult.unmatched} unmatched`);
    } catch (e) {
      stopFlushing();
      const msg = e instanceof Error ? e.message : "Scan failed";
      pushLog({ phase: "error", message: msg, percent: 0 });
      setScanPhase("error");
      toast.error("Scan failed", msg);
    } finally {
      abortRef.current = null;
      setIsScanning(false);
    }
  };

  if (!game) {
    return <p className="text-text-muted">Loading game...</p>;
  }

  const matched = mods.filter((m) => m.nexus_match).length;
  const enabledCount = installedMods.filter((m) => !m.disabled).length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-text-primary">{game.name}</h1>
            {gameVersion?.version && (
              <span className="text-xs font-medium text-text-muted bg-surface-secondary px-2 py-0.5 rounded">
                v{gameVersion.version}
              </span>
            )}
          </div>
          <p className="text-sm text-text-muted">{game.install_path}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={handleLaunch} loading={isLaunching} disabled={!gameVersion?.exe_path}>
            <Play size={16} /> Play
          </Button>
          <Button onClick={handleFullScan} loading={isScanning}>
            <Scan size={16} /> Scan & Correlate
          </Button>
        </div>
      </div>

      {scanPhase && (
        <ScanProgress logs={scanLogs} percent={scanPercent} phase={scanPhase} />
      )}

      <div className="grid grid-cols-4 gap-4">
        <Card>
          <div className="flex items-center gap-3">
            <Package size={18} className="text-success" />
            <div>
              <p className="text-xs text-text-muted">Scanned Mods</p>
              <p className="text-lg font-bold text-text-primary">{mods.length}</p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-3">
            <UserCheck size={18} className="text-accent" />
            <div>
              <p className="text-xs text-text-muted">Installed</p>
              <p className="text-lg font-bold text-text-primary">
                {enabledCount}/{installedMods.length}
              </p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-3">
            <Link2 size={18} className="text-warning" />
            <div>
              <p className="text-xs text-text-muted">Nexus Matched</p>
              <p className="text-lg font-bold text-text-primary">{matched}</p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-3">
            <RefreshCw size={18} className="text-danger" />
            <div>
              <p className="text-xs text-text-muted">Updates</p>
              <p className="text-lg font-bold text-text-primary">
                {updates?.updates_available ?? "--"}
              </p>
            </div>
          </div>
        </Card>
      </div>

      <div className="flex gap-1 border-b border-border">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              "px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px",
              tab === key
                ? "border-accent text-accent"
                : "border-transparent text-text-muted hover:text-text-secondary",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "mods" && <ModsTable mods={mods} />}
      {tab === "installed" && (
        <InstalledModsTable mods={installedMods} gameName={name} />
      )}
      {tab === "archives" && (
        <ArchivesList archives={archives} gameName={name} />
      )}
      {tab === "profiles" && (
        <ProfileManager profiles={profiles} gameName={name} />
      )}
      {tab === "updates" && (
        <UpdatesTab gameName={name} updates={updates?.updates ?? []} />
      )}
    </div>
  );
}
