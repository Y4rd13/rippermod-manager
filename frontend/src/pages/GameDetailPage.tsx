import {
  Archive,
  Download,
  Eye,
  FolderOpen,
  Heart,
  Link2,
  Package,
  Play,
  RefreshCw,
  Scan,
  Search,
  TrendingUp,
  UserCheck,
} from "lucide-react";
import { invoke } from "@tauri-apps/api/core";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router";

import { ArchivesList } from "@/components/mods/ArchivesList";
import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { InstalledModsTable } from "@/components/mods/InstalledModsTable";
import { ModCardAction } from "@/components/mods/ModCardAction";
import { ModDetailModal } from "@/components/mods/ModDetailModal";
import { ModsTable } from "@/components/mods/ModsTable";
import { NexusAccountGrid } from "@/components/mods/NexusAccountGrid";
import { NexusMatchedGrid } from "@/components/mods/NexusMatchedGrid";
import { TrendingGrid } from "@/components/mods/TrendingGrid";
import { ProfileManager } from "@/components/mods/ProfileManager";
import { SourceBadge } from "@/components/mods/SourceBadge";
import { UpdateDownloadCell } from "@/components/mods/UpdateDownloadCell";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { ScanProgress, type ScanLog } from "@/components/ui/ScanProgress";
import { SkeletonTable } from "@/components/ui/SkeletonTable";
import { Switch } from "@/components/ui/Switch";
import { useCheckUpdates, useStartDownload } from "@/hooks/mutations";
import { useInstallFlow } from "@/hooks/use-install-flow";
import {
  useAvailableArchives,
  useDownloadJobs,
  useEndorsedMods,
  useGame,
  useGameVersion,
  useInstalledMods,
  useMods,
  useProfiles,
  useSettings,
  useTrackedMods,
  useTrendingMods,
  useUpdates,
} from "@/hooks/queries";
import { api } from "@/lib/api-client";
import { timeAgo } from "@/lib/format";
import { parseSSE } from "@/lib/sse-parser";
import { cn } from "@/lib/utils";
import { toast } from "@/stores/toast-store";
import type { ModUpdate } from "@/types/api";

type Tab = "installed" | "updates" | "trending" | "endorsed" | "tracked" | "mods" | "matched" | "archives" | "profiles";

const TABS: { key: Tab; label: string; Icon: typeof Package }[] = [
  { key: "installed", label: "Installed", Icon: UserCheck },
  { key: "updates", label: "Updates", Icon: RefreshCw },
  { key: "trending", label: "Trending", Icon: TrendingUp },
  { key: "endorsed", label: "Endorsed", Icon: Heart },
  { key: "tracked", label: "Tracked", Icon: Eye },
  { key: "mods", label: "Scanned", Icon: Package },
  { key: "matched", label: "Nexus Matched", Icon: Link2 },
  { key: "archives", label: "Archives", Icon: Archive },
  { key: "profiles", label: "Profiles", Icon: FolderOpen },
];

type UpdateSortKey = "name" | "author" | "source" | "updated";

const UPDATE_SORT_OPTIONS: { value: UpdateSortKey; label: string }[] = [
  { value: "name", label: "Name" },
  { value: "author", label: "Author" },
  { value: "source", label: "Source" },
  { value: "updated", label: "Last Updated" },
];

function UpdatesTab({ gameName, updates, isLoading }: { gameName: string; updates: ModUpdate[]; isLoading?: boolean }) {
  const { data: downloadJobs = [] } = useDownloadJobs(gameName);
  const checkUpdates = useCheckUpdates();
  const startDownload = useStartDownload();
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<UpdateSortKey>("name");
  const [chip, setChip] = useState("all");

  const filteredUpdates = useMemo(() => {
    const q = filter.toLowerCase();
    const items = updates.filter((u) => {
      if (q && !u.display_name.toLowerCase().includes(q) && !u.author.toLowerCase().includes(q)) return false;
      if (chip !== "all" && u.source !== chip) return false;
      return true;
    });

    items.sort((a, b) => {
      switch (sortKey) {
        case "name":
          return a.display_name.localeCompare(b.display_name);
        case "author":
          return a.author.localeCompare(b.author);
        case "source":
          return a.source.localeCompare(b.source);
        case "updated":
          return (b.nexus_timestamp ?? 0) - (a.nexus_timestamp ?? 0);
      }
    });

    return items;
  }, [updates, filter, sortKey, chip]);

  const downloadableUpdates = filteredUpdates.filter((u) => u.nexus_file_id != null);

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

  const updateChips = useMemo(() => {
    const sources = new Set(updates.map((u) => u.source));
    const chips = [{ key: "all", label: "All" }];
    if (sources.has("installed")) chips.push({ key: "installed", label: "Installed" });
    if (sources.has("correlation")) chips.push({ key: "correlation", label: "Matched" });
    if (sources.has("endorsed")) chips.push({ key: "endorsed", label: "Endorsed" });
    if (sources.has("tracked")) chips.push({ key: "tracked", label: "Tracked" });
    return chips;
  }, [updates]);

  if (isLoading) return <SkeletonTable columns={7} rows={5} />;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="Filter by name or author..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="w-full rounded-lg border border-border bg-surface-2 py-1.5 pl-8 pr-3 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
          />
        </div>
        <select
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as UpdateSortKey)}
          className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
        >
          {UPDATE_SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <span className="text-xs text-text-muted">
          {filteredUpdates.length} update{filteredUpdates.length !== 1 ? "s" : ""}
        </span>
        <div className="ml-auto flex items-center gap-2">
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

      {updateChips.length > 2 && (
        <FilterChips chips={updateChips} active={chip} onChange={setChip} />
      )}

      {!updates.length ? (
        <EmptyState
          icon={RefreshCw}
          title="No Updates Found"
          description="Run a scan first, then check for updates to find newer versions of your mods."
          actions={
            <Button
              size="sm"
              onClick={() => checkUpdates.mutate(gameName)}
              loading={checkUpdates.isPending}
            >
              Check Now
            </Button>
          }
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text-muted sticky top-0 z-10 bg-surface-0">
                <th className="py-2 pr-4">Mod</th>
                <th className="py-2 pr-4">Local Version</th>
                <th className="py-2 pr-4">Nexus Version</th>
                <th className="py-2 pr-4">Source</th>
                <th className="py-2 pr-4">Author</th>
                <th className="py-2 pr-4">Updated</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {filteredUpdates.map((u, i) => (
                <tr
                  key={u.installed_mod_id ?? `group-${u.mod_group_id ?? i}`}
                  className="border-b border-border/50"
                >
                  <td className="py-2 pr-4 text-text-primary">{u.display_name}</td>
                  <td className="py-2 pr-4 text-text-muted">{u.local_version}</td>
                  <td className="py-2 pr-4 text-success font-medium">{u.nexus_version}</td>
                  <td className="py-2 pr-4">
                    <SourceBadge source={u.source} />
                  </td>
                  <td className="py-2 pr-4 text-text-muted">{u.author}</td>
                  <td className="py-2 pr-4 text-text-muted">
                    {u.nexus_timestamp ? timeAgo(u.nexus_timestamp) : "—"}
                  </td>
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
  const { data: mods = [], isLoading: modsLoading } = useMods(name);
  const { data: installedMods = [], isLoading: installedLoading } = useInstalledMods(name);
  const { data: archives = [], isLoading: archivesLoading } = useAvailableArchives(name);
  const { data: profiles = [], isLoading: profilesLoading } = useProfiles(name);
  const { data: endorsedMods = [], isLoading: endorsedLoading } = useEndorsedMods(name);
  const { data: trackedMods = [], isLoading: trackedLoading } = useTrackedMods(name);
  const { data: trendingResult, isLoading: trendingLoading } = useTrendingMods(name);
  const { data: updates, isLoading: updatesLoading } = useUpdates(name);
  const { data: downloadJobs = [] } = useDownloadJobs(name);
  const { data: settings = [] } = useSettings();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("installed");
  const [selectedModId, setSelectedModId] = useState<number | null>(null);
  const [aiSearch, setAiSearch] = useState(false);
  const hasOpenaiKey = settings.some((s) => s.key === "openai_api_key" && s.value);

  const modalFlow = useInstallFlow(name, archives, downloadJobs);

  const installedModIds = useMemo(
    () => new Set(installedMods.filter((m) => m.nexus_mod_id != null).map((m) => m.nexus_mod_id!)),
    [installedMods],
  );

  const [isLaunching, setIsLaunching] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [scanLogs, setScanLogs] = useState<ScanLog[]>([]);
  const [scanPercent, setScanPercent] = useState(0);
  const [scanPhase, setScanPhase] = useState("");

  const prevCompletedRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    const completedIds = new Set(
      downloadJobs.filter((j) => j.status === "completed").map((j) => j.id),
    );
    if (prevCompletedRef.current.size > 0) {
      const hasNew = [...completedIds].some((id) => !prevCompletedRef.current.has(id));
      if (hasNew) {
        queryClient.invalidateQueries({ queryKey: ["available-archives", name] });
      }
    }
    prevCompletedRef.current = completedIds;
  }, [downloadJobs, name, queryClient]);

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
        aiSearch ? { ai_search: true } : undefined,
        controller.signal,
      );

      for await (const event of parseSSE(response)) {
        const data = JSON.parse(event.data) as ScanLog;
        pushLog(data);
      }

      stopFlushing();
      setScanPhase("done");
      setScanPercent(100);
      queryClient.invalidateQueries({ queryKey: ["mods", name] });
      queryClient.invalidateQueries({ queryKey: ["installed-mods", name] });
      queryClient.invalidateQueries({ queryKey: ["nexus-downloads", name] });
      queryClient.invalidateQueries({ queryKey: ["available-archives", name] });
      toast.success("Scan complete");
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

  const updateByNexusId = useMemo(() => {
    const map = new Map<number, ModUpdate>();
    for (const u of updates?.updates ?? []) map.set(u.nexus_mod_id, u);
    return map;
  }, [updates]);

  const nexusMatched = useMemo(() => mods.filter((m) => m.nexus_match), [mods]);
  const enabledCount = installedMods.filter((m) => !m.disabled).length;

  const tabCounts = useMemo<Partial<Record<Tab, number>>>(() => ({
    installed: installedLoading ? undefined : installedMods.length,
    updates: updatesLoading ? undefined : updates?.updates_available,
    trending: trendingLoading ? undefined : (trendingResult?.trending.length ?? 0) + (trendingResult?.latest_updated.length ?? 0),
    endorsed: endorsedLoading ? undefined : endorsedMods.length,
    tracked: trackedLoading ? undefined : trackedMods.length,
    mods: modsLoading ? undefined : mods.length,
    matched: modsLoading ? undefined : nexusMatched.length,
    archives: archivesLoading ? undefined : archives.length,
    profiles: profilesLoading ? undefined : profiles.length,
  }), [
    installedMods.length, installedLoading,
    updates?.updates_available, updatesLoading,
    trendingResult, trendingLoading,
    endorsedMods.length, endorsedLoading,
    trackedMods.length, trackedLoading,
    mods.length, modsLoading,
    nexusMatched.length,
    archives.length, archivesLoading,
    profiles.length, profilesLoading,
  ]);

  if (!game) {
    return <p className="text-text-muted">Loading game...</p>;
  }

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
          {hasOpenaiKey && (
            <Switch checked={aiSearch} onChange={setAiSearch} label="AI Search" disabled={isScanning} />
          )}
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
        <Card
          className="hover:border-warning/40 transition-colors"
          onClick={() => setTab("matched")}
        >
          <div className="flex items-center gap-3">
            <Link2 size={18} className="text-warning" />
            <div>
              <p className="text-xs text-text-muted">Nexus Matched</p>
              <p className="text-lg font-bold text-text-primary">{nexusMatched.length}</p>
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

      <div className="flex gap-1 border-b border-border overflow-x-auto">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              "px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap flex items-center gap-1",
              tab === key
                ? "border-accent text-accent"
                : "border-transparent text-text-muted hover:text-text-secondary",
            )}
          >
            {label}
            {tabCounts[key] != null && (
              <span className="text-xs tabular-nums opacity-60">
                {tabCounts[key]}
              </span>
            )}
            {key === "updates" && (updates?.updates_available ?? 0) > 0 && (
              <span className="h-1.5 w-1.5 rounded-full bg-warning inline-block" />
            )}
          </button>
        ))}
      </div>

      <div key={tab} className="animate-fade-in">
      {tab === "mods" && <ModsTable mods={mods} isLoading={modsLoading} />}
      {tab === "matched" && (
        <NexusMatchedGrid
          mods={nexusMatched}
          archives={archives}
          installedMods={installedMods}
          gameName={name}
          downloadJobs={downloadJobs}
          isLoading={modsLoading}
          onModClick={setSelectedModId}
        />
      )}
      {tab === "endorsed" && (
        <NexusAccountGrid
          mods={endorsedMods}
          archives={archives}
          installedMods={installedMods}
          gameName={name}
          emptyIcon="heart"
          emptyTitle="No Endorsed Mods"
          emptyMessage="Sync your Nexus account to see mods you've endorsed."
          downloadJobs={downloadJobs}
          isLoading={endorsedLoading}
          onModClick={setSelectedModId}
        />
      )}
      {tab === "tracked" && (
        <NexusAccountGrid
          mods={trackedMods}
          archives={archives}
          installedMods={installedMods}
          gameName={name}
          emptyIcon="eye"
          emptyTitle="No Tracked Mods"
          emptyMessage="Sync your Nexus account to see mods you're tracking."
          downloadJobs={downloadJobs}
          isLoading={trackedLoading}
          onModClick={setSelectedModId}
        />
      )}
      {tab === "trending" && (
        <TrendingGrid
          trendingMods={trendingResult?.trending ?? []}
          latestUpdatedMods={trendingResult?.latest_updated ?? []}
          archives={archives}
          installedMods={installedMods}
          gameName={name}
          downloadJobs={downloadJobs}
          isLoading={trendingLoading}
          onModClick={setSelectedModId}
        />
      )}
      {tab === "installed" && (
        <InstalledModsTable
          mods={installedMods}
          gameName={name}
          recognizedMods={nexusMatched}
          archives={archives}
          downloadJobs={downloadJobs}
          updates={updates?.updates ?? []}
          isLoading={installedLoading}
          onModClick={setSelectedModId}
          onTabChange={(t) => setTab(t as Tab)}
        />
      )}
      {tab === "archives" && (
        <ArchivesList archives={archives} gameName={name} isLoading={archivesLoading} />
      )}
      {tab === "profiles" && (
        <ProfileManager profiles={profiles} gameName={name} isLoading={profilesLoading} />
      )}
      {tab === "updates" && (
        <UpdatesTab gameName={name} updates={updates?.updates ?? []} isLoading={updatesLoading} />
      )}
      </div>

      {selectedModId != null && (() => {
        const modUpdate = updateByNexusId.get(selectedModId);
        const archive = modalFlow.archiveByModId.get(selectedModId);
        return (
          <ModDetailModal
            gameDomain={game.domain_name}
            modId={selectedModId}
            update={modUpdate}
            action={
              modUpdate ? (
                <UpdateDownloadCell
                  update={modUpdate}
                  gameName={name}
                  downloadJobs={downloadJobs}
                />
              ) : (
                <ModCardAction
                  isInstalled={installedModIds.has(selectedModId)}
                  isInstalling={modalFlow.installingModIds.has(selectedModId)}
                  activeDownload={modalFlow.activeDownloadByModId.get(selectedModId)}
                  completedDownload={modalFlow.completedDownloadByModId.get(selectedModId)}
                  archive={archive}
                  hasConflicts={modalFlow.conflicts != null}
                  isDownloading={modalFlow.downloadingModId === selectedModId}
                  onInstall={() => archive && modalFlow.handleInstall(selectedModId, archive)}
                  onInstallByFilename={() => {
                    const dl = modalFlow.completedDownloadByModId.get(selectedModId);
                    if (dl) modalFlow.handleInstallByFilename(selectedModId, dl.file_name);
                  }}
                  onDownload={() => modalFlow.handleDownload(selectedModId)}
                  onCancelDownload={() => {
                    const dl = modalFlow.activeDownloadByModId.get(selectedModId);
                    if (dl) modalFlow.handleCancelDownload(dl.id);
                  }}
                />
              )
            }
            onClose={() => setSelectedModId(null)}
          />
        );
      })()}

      {modalFlow.conflicts && (
        <ConflictDialog
          conflicts={modalFlow.conflicts}
          onCancel={modalFlow.dismissConflicts}
          onSkip={modalFlow.handleInstallWithSkip}
          onOverwrite={modalFlow.handleInstallOverwrite}
        />
      )}
    </div>
  );
}
