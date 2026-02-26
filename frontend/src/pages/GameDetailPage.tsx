import {
  Archive,
  ChevronRight,
  Eye,
  FolderOpen,
  GitBranch,
  Heart,
  Link2,
  Package,
  Play,
  RefreshCw,
  Scan,
  Sparkles,
  TrendingUp,
  UserCheck,
} from "lucide-react";
import { invoke } from "@tauri-apps/api/core";
import { useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router";

import { ArchivesList } from "@/components/mods/ArchivesList";
import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { FomodWizard } from "@/components/mods/FomodWizard";
import { InstalledModsTable } from "@/components/mods/InstalledModsTable";
import { ModCardAction } from "@/components/mods/ModCardAction";
import { ModDetailModal } from "@/components/mods/ModDetailModal";
import { ModsTable } from "@/components/mods/ModsTable";
import { NexusAccountGrid } from "@/components/mods/NexusAccountGrid";
import { NexusMatchedGrid } from "@/components/mods/NexusMatchedGrid";
import { TrendingGrid } from "@/components/mods/TrendingGrid";
import { ProfileManager } from "@/components/mods/ProfileManager";
import { UpdateDownloadCell } from "@/components/mods/UpdateDownloadCell";
import { UpdatesTable } from "@/components/mods/UpdatesTable";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ScanProgress, type ScanLog } from "@/components/ui/ScanProgress";
import { Switch } from "@/components/ui/Switch";
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
  useHasOpenaiKey,
  useTrackedMods,
  useTrendingMods,
  useUpdates,
} from "@/hooks/queries";
import { api } from "@/lib/api-client";
import { parseSSE } from "@/lib/sse-parser";
import { cn } from "@/lib/utils";
import { toast } from "@/stores/toast-store";
import { SkeletonCardGrid } from "@/components/ui/SkeletonCard";
import type { ModUpdate } from "@/types/api";

const ConflictGraphTab = lazy(() =>
  import("@/components/conflicts/ConflictGraphTab").then((m) => ({
    default: m.ConflictGraphTab,
  })),
);

type Tab = "installed" | "updates" | "trending" | "endorsed" | "tracked" | "mods" | "matched" | "archives" | "profiles" | "conflicts";

const TABS: { key: Tab; label: string; Icon: typeof Package; tooltip: string }[] = [
  { key: "installed", label: "Installed", Icon: UserCheck, tooltip: "Managed and recognized mods on your system" },
  { key: "updates", label: "Updates", Icon: RefreshCw, tooltip: "Mods with newer versions available on Nexus" },
  { key: "trending", label: "Trending", Icon: TrendingUp, tooltip: "Popular and recently updated mods on Nexus" },
  { key: "endorsed", label: "Endorsed", Icon: Heart, tooltip: "Mods you've endorsed on your Nexus account" },
  { key: "tracked", label: "Tracked", Icon: Eye, tooltip: "Mods you're tracking on your Nexus account" },
  { key: "mods", label: "Scanned", Icon: Package, tooltip: "All mod file groups found by scanning your game folder" },
  { key: "matched", label: "Nexus Matched", Icon: Link2, tooltip: "Scanned mods matched to Nexus Mods entries" },
  { key: "archives", label: "Archives", Icon: Archive, tooltip: "Downloaded mod archives ready to install" },
  { key: "profiles", label: "Profiles", Icon: FolderOpen, tooltip: "Saved snapshots of your mod enabled/disabled states" },
  { key: "conflicts", label: "Conflicts", Icon: GitBranch, tooltip: "Visualize file conflicts between mods and archives" },
];

export function GameDetailPage() {
  const { name = "" } = useParams();
  const { data: game } = useGame(name);
  const { data: gameVersion } = useGameVersion(name);
  const { data: mods = [], isLoading: modsLoading } = useMods(name);
  const { data: installedMods = [], isLoading: installedLoading } = useInstalledMods(name);
  const { data: archives = [], isLoading: archivesLoading } = useAvailableArchives(name);
  const { data: profiles = [], isLoading: profilesLoading } = useProfiles(name);
  const { data: endorsedMods = [], isLoading: endorsedLoading, dataUpdatedAt: endorsedUpdatedAt } = useEndorsedMods(name);
  const { data: trackedMods = [], isLoading: trackedLoading, dataUpdatedAt: trackedUpdatedAt } = useTrackedMods(name);
  const { data: trendingResult, isLoading: trendingLoading, dataUpdatedAt: trendingUpdatedAt } = useTrendingMods(name);
  const { data: updates, isLoading: updatesLoading } = useUpdates(name);
  const { data: downloadJobs = [] } = useDownloadJobs(name);
  const hasOpenaiKey = useHasOpenaiKey();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("installed");
  const [selectedModId, setSelectedModId] = useState<number | null>(null);
  const [aiSearch, setAiSearch] = useState(() => {
    try {
      const stored = localStorage.getItem("ai-search-enabled");
      if (stored !== null) return JSON.parse(stored) === true;
    } catch { /* ignore */ }
    return false;
  });
  useEffect(() => {
    if (localStorage.getItem("ai-search-enabled") === null) {
      setAiSearch(!!hasOpenaiKey);
    }
  }, [hasOpenaiKey]);
  const handleAiSearchChange = (v: boolean) => {
    setAiSearch(v);
    try { localStorage.setItem("ai-search-enabled", JSON.stringify(v)); } catch { /* ignore */ }
  };

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

  const recognizedNotInstalled = useMemo(() => {
    const installedIds = new Set(installedMods.filter((m) => m.nexus_mod_id != null).map((m) => m.nexus_mod_id!));
    return nexusMatched.filter((m) => m.nexus_match && !installedIds.has(m.nexus_match.nexus_mod_id)).length;
  }, [nexusMatched, installedMods]);

  const tabCounts = useMemo<Partial<Record<Tab, number>>>(() => ({
    installed: installedLoading ? undefined : installedMods.length + recognizedNotInstalled,
    updates: updatesLoading ? undefined : updates?.updates_available,
    trending: trendingLoading ? undefined : (trendingResult?.trending.length ?? 0) + (trendingResult?.latest_updated.length ?? 0),
    endorsed: endorsedLoading ? undefined : endorsedMods.length,
    tracked: trackedLoading ? undefined : trackedMods.length,
    mods: modsLoading ? undefined : mods.length,
    matched: modsLoading ? undefined : nexusMatched.length,
    archives: archivesLoading ? undefined : archives.length,
    profiles: profilesLoading ? undefined : profiles.length,
  }), [
    installedMods.length, installedLoading, recognizedNotInstalled,
    updates?.updates_available, updatesLoading,
    trendingResult, trendingLoading,
    endorsedMods.length, endorsedLoading,
    trackedMods.length, trackedLoading,
    mods.length, modsLoading,
    nexusMatched.length,
    archives.length, archivesLoading,
    profiles.length, profilesLoading,
  ]);

  const tabsRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const rafRef = useRef(0);

  const updateScrollIndicators = useCallback(() => {
    const el = tabsRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 0);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  }, []);

  useEffect(() => {
    updateScrollIndicators();
    const el = tabsRef.current;
    if (!el) return;
    const observer = new ResizeObserver(updateScrollIndicators);
    observer.observe(el);
    return () => observer.disconnect();
  }, [updateScrollIndicators]);

  const handleTabScroll = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(updateScrollIndicators);
  }, [updateScrollIndicators]);

  if (!game) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-4 w-32 bg-surface-2 rounded" />
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <div className="h-7 w-48 bg-surface-2 rounded" />
            <div className="h-4 w-72 bg-surface-2 rounded" />
          </div>
          <div className="flex gap-2">
            <div className="h-9 w-20 bg-surface-2 rounded-lg" />
            <div className="h-9 w-36 bg-surface-2 rounded-lg" />
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="rounded-xl border border-border bg-surface-1 p-5">
              <div className="flex items-center gap-3">
                <div className="h-5 w-5 bg-surface-2 rounded" />
                <div className="space-y-1.5 flex-1">
                  <div className="h-3 w-20 bg-surface-2 rounded" />
                  <div className="h-5 w-10 bg-surface-2 rounded" />
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="flex gap-1 border-b border-border">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="h-9 w-20 bg-surface-2 rounded mb-px" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-sm text-text-muted">
        <Link to="/games" className="hover:text-text-primary transition-colors">
          Games
        </Link>
        <ChevronRight size={14} />
        <span className="text-text-primary font-medium">{game.name}</span>
      </nav>

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
          <Button variant="secondary" onClick={handleLaunch} loading={isLaunching} disabled={!gameVersion?.exe_path} title="Launch the game executable">
            <Play size={16} /> Play
          </Button>
          <span
            title={
              hasOpenaiKey
                ? "Use AI-powered semantic search to improve mod matching accuracy (uses OpenAI API)"
                : "Add your OpenAI API key in Settings to enable AI Search"
            }
            className="flex items-center gap-1.5"
          >
            <Sparkles size={16} className={cn(aiSearch && hasOpenaiKey ? "text-accent" : "text-text-muted")} />
            <Switch
              checked={aiSearch}
              onChange={handleAiSearchChange}
              label="AI Search"
              disabled={isScanning || !hasOpenaiKey}
            />
          </span>
          <Button onClick={handleFullScan} loading={isScanning} title="Scan game folder for mods, group files, and match them to Nexus Mods">
            <Scan size={16} /> Scan & Correlate
          </Button>
        </div>
      </div>

      {scanPhase && (
        <ScanProgress logs={scanLogs} percent={scanPercent} phase={scanPhase} />
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card
          className="hover:border-success/40 transition-colors"
          onClick={() => setTab("mods")}
          title="Total mod groups found by scanning your game folder"
        >
          <div className="flex items-center gap-3">
            <Package size={18} className="text-success" />
            <div>
              <p className="text-xs text-text-muted">Scanned Mods</p>
              <p className="text-lg font-bold text-text-primary">{mods.length}</p>
            </div>
          </div>
        </Card>
        <Card
          className="hover:border-accent/40 transition-colors"
          onClick={() => setTab("installed")}
          title="Mods managed through this app (enabled / total)"
        >
          <div className="flex items-center gap-3">
            <UserCheck size={18} className="text-accent" />
            <div>
              <p className="text-xs text-text-muted">Managed</p>
              <p className="text-lg font-bold text-text-primary">
                {enabledCount}/{installedMods.length}
              </p>
            </div>
          </div>
        </Card>
        <Card
          className="hover:border-warning/40 transition-colors"
          onClick={() => setTab("matched")}
          title="Scanned mods matched to Nexus Mods entries"
        >
          <div className="flex items-center gap-3">
            <Link2 size={18} className="text-warning" />
            <div>
              <p className="text-xs text-text-muted">Nexus Matched</p>
              <p className="text-lg font-bold text-text-primary">{nexusMatched.length}</p>
            </div>
          </div>
        </Card>
        <Card
          className="hover:border-danger/40 transition-colors"
          onClick={() => setTab("updates")}
          title="Newer versions available on Nexus for your mods"
        >
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

      <div className="relative">
        {canScrollLeft && (
          <div className="pointer-events-none absolute left-0 top-0 bottom-0 w-8 z-10 bg-gradient-to-r from-surface-0 to-transparent" />
        )}
        <div
          ref={tabsRef}
          onScroll={handleTabScroll}
          className="flex gap-1 border-b border-border overflow-x-auto scrollbar-none"
        >
          {TABS.map(({ key, label, tooltip }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              title={tooltip}
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
        {canScrollRight && (
          <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 z-10 bg-gradient-to-l from-surface-0 to-transparent" />
        )}
      </div>

      <div key={tab} className="animate-fade-in">
      {tab === "mods" && <ModsTable mods={mods} gameName={name} isLoading={modsLoading} />}
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
          dataUpdatedAt={endorsedUpdatedAt}
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
          dataUpdatedAt={trackedUpdatedAt}
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
          dataUpdatedAt={trendingUpdatedAt}
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
        <ProfileManager profiles={profiles} gameName={name} isLoading={profilesLoading} installedCount={installedMods.length} recognizedCount={recognizedNotInstalled} />
      )}
      {tab === "updates" && (
        <UpdatesTable gameName={name} updates={updates?.updates ?? []} isLoading={updatesLoading} />
      )}
      {tab === "conflicts" && (
        <Suspense fallback={<SkeletonCardGrid count={3} />}>
          <ConflictGraphTab gameName={name} />
        </Suspense>
      )}
      </div>

      {(() => {
        const effectiveModId = selectedModId ?? modalFlow.fileSelectModId;
        if (effectiveModId == null) return null;
        const effectiveDefaultTab = modalFlow.fileSelectModId != null && selectedModId == null ? "files" as const : undefined;
        const modUpdate = updateByNexusId.get(effectiveModId);
        const archive = modalFlow.archiveByModId.get(effectiveModId);
        return (
          <ModDetailModal
            gameDomain={game.domain_name}
            gameName={name}
            modId={effectiveModId}
            update={modUpdate}
            defaultTab={effectiveDefaultTab}
            action={
              modUpdate ? (
                <UpdateDownloadCell
                  update={modUpdate}
                  gameName={name}
                  downloadJobs={downloadJobs}
                />
              ) : (
                <ModCardAction
                  isInstalled={installedModIds.has(effectiveModId)}
                  isInstalling={modalFlow.installingModIds.has(effectiveModId)}
                  activeDownload={modalFlow.activeDownloadByModId.get(effectiveModId)}
                  completedDownload={modalFlow.completedDownloadByModId.get(effectiveModId)}
                  archive={archive}
                  hasConflicts={modalFlow.conflicts != null}
                  isDownloading={modalFlow.downloadingModId === effectiveModId}
                  onInstall={() => archive && modalFlow.handleInstall(effectiveModId, archive)}
                  onInstallByFilename={() => {
                    const dl = modalFlow.completedDownloadByModId.get(effectiveModId);
                    if (dl) modalFlow.handleInstallByFilename(effectiveModId, dl.file_name);
                  }}
                  onDownload={() => modalFlow.handleDownload(effectiveModId)}
                  onCancelDownload={() => {
                    const dl = modalFlow.activeDownloadByModId.get(effectiveModId);
                    if (dl) modalFlow.handleCancelDownload(dl.id);
                  }}
                />
              )
            }
            onClose={() => {
              setSelectedModId(null);
              modalFlow.dismissFileSelect();
            }}
          />
        );
      })()}

      {modalFlow.fomodArchive && (
        <FomodWizard
          gameName={name}
          archiveFilename={modalFlow.fomodArchive}
          onDismiss={modalFlow.dismissFomod}
          onInstallComplete={modalFlow.dismissFomod}
        />
      )}

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
