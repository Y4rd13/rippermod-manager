import {
  AlertTriangle,
  Archive,
  ChevronRight,
  Eye,
  FolderOpen,
  Heart,
  Link2,
  Package,
  Play,
  RefreshCw,
  Scan,
  TrendingUp,
  UserCheck,
  X,
} from "lucide-react";
import { invoke } from "@tauri-apps/api/core";
import { useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router";

import { ClusterDetailsPanel, ConflictSummaryWidget } from "@/components/conflicts/ConflictSummaryWidget";
import { AdoptReviewDialog } from "@/components/mods/AdoptReviewDialog";
import { FrameworksStatCard } from "@/components/FrameworksStatCard";
import { FrameworksWidget } from "@/components/FrameworksWidget";
import { HealthStatCard } from "@/components/HealthStatCard";
import { HealthWidget } from "@/components/HealthWidget";
import { LogErrorsWidget } from "@/components/LogErrorsWidget";
import { ArchivesList } from "@/components/mods/ArchivesList";
import { InstalledCollectionsSection } from "@/components/collections/InstalledCollectionsSection";
import { ConflictDialog } from "@/components/mods/ConflictDialog";
import { ConflictsInbox } from "@/components/mods/ConflictsInbox";
import { FomodWizard } from "@/components/mods/FomodWizard";
import { PreInstallPreview } from "@/components/mods/PreInstallPreview";
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
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ScanProgress, type ScanLog } from "@/components/ui/ScanProgress";
import { useDeploy } from "@/hooks/use-deploy";
import { useInstallFlow } from "@/hooks/use-install-flow";
import {
  useAvailableArchives,
  useConflictsOverview,
  useDownloadJobs,
  useEndorsedMods,
  useGame,
  useGameVersion,
  useInstalledMods,
  useMods,
  useProfiles,
  useTrackedMods,
  useTrendingMods,
  useUpdates,
} from "@/hooks/queries";
import { api } from "@/lib/api-client";
import { parseSSE } from "@/lib/sse-parser";
import { cn } from "@/lib/utils";
import { toast } from "@/stores/toast-store";
import { useUIStore } from "@/stores/ui-store";
import { SkeletonCardGrid } from "@/components/ui/SkeletonCard";
import type { HealthReport, ModUpdate } from "@/types/api";

const ArchiveResourceConflicts = lazy(() =>
  import("@/components/conflicts/ArchiveResourceConflicts").then((m) => ({
    default: m.ArchiveResourceConflicts,
  })),
);

const LoadOrderView = lazy(() =>
  import("@/components/conflicts/LoadOrderView").then((m) => ({
    default: m.LoadOrderView,
  })),
);

type MatchedSubTab = "nexus-matched" | "scan-details";

const MATCHED_SUB_TABS: { key: MatchedSubTab; label: string }[] = [
  { key: "nexus-matched", label: "Nexus Matched" },
  { key: "scan-details", label: "Scan Details" },
];

type ConflictSubTab = "file-conflicts" | "archive-resources" | "cluster-details" | "load-order";

function ConflictSubTabs({ gameName, gameDomain }: { gameName: string; gameDomain: string }) {
  const [subTab, setSubTab] = useState<ConflictSubTab>("file-conflicts");
  const subTabs: { key: ConflictSubTab; label: string }[] = [
    { key: "file-conflicts", label: "File Conflicts" },
    { key: "archive-resources", label: "Archive Resources" },
    { key: "load-order", label: "Load Order" },
    { key: "cluster-details", label: "Cluster Details" },
  ];
  return (
    <div className="space-y-4">
      <LogErrorsWidget gameName={gameName} />
      <ConflictSummaryWidget gameName={gameName} />
      <div className="flex gap-1 border-b border-border">
        {subTabs.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setSubTab(key)}
            className={cn(
              "px-3 py-1.5 text-sm font-medium transition-colors border-b-2 -mb-px",
              subTab === key
                ? "border-accent text-accent"
                : "border-transparent text-text-muted hover:text-text-secondary",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {subTab === "file-conflicts" && <ConflictsInbox gameName={gameName} />}
      {subTab === "archive-resources" && (
        <Suspense fallback={<SkeletonCardGrid count={3} />}>
          <ArchiveResourceConflicts gameName={gameName} gameDomain={gameDomain} />
        </Suspense>
      )}
      {subTab === "cluster-details" && <ClusterDetailsPanel gameName={gameName} />}
      {subTab === "load-order" && (
        <Suspense fallback={<SkeletonCardGrid count={3} />}>
          <LoadOrderView gameName={gameName} />
        </Suspense>
      )}
    </div>
  );
}

type Tab = "installed" | "matched" | "archives" | "updates" | "conflicts" | "profiles" | "trending" | "endorsed" | "tracked";

const TABS: { key: Tab; label: string; Icon: typeof Package; description: string }[] = [
  // Management
  { key: "installed", label: "Installed", Icon: UserCheck, description: "Mods currently installed on your game. Toggle on/off, uninstall, or check deploy drift." },
  { key: "archives", label: "Archives", Icon: Archive, description: "Mod archives in your downloaded_mods folder, ready to install." },
  { key: "updates", label: "Updates", Icon: RefreshCw, description: "Newer versions of your installed mods available on Nexus." },
  { key: "conflicts", label: "Conflicts", Icon: AlertTriangle, description: "File and resource conflicts between your installed mods." },
  { key: "profiles", label: "Profiles", Icon: FolderOpen, description: "Save and switch between enabled/disabled mod snapshots." },
  // Discovery & Nexus account
  { key: "matched", label: "Matched", Icon: Link2, description: "Mods detected on disk and correlated against Nexus." },
  { key: "trending", label: "Trending", Icon: TrendingUp, description: "Popular and recently updated mods on Nexus." },
  { key: "endorsed", label: "Endorsed", Icon: Heart, description: "Mods you've endorsed on your Nexus account." },
  { key: "tracked", label: "Tracked", Icon: Eye, description: "Mods you're tracking on your Nexus account." },
];

export function GameDetailPage() {
  const { name = "" } = useParams();
  const setActiveGame = useUIStore((s) => s.setActiveGame);
  const warnBeforeLaunch = useUIStore((s) => s.warnBeforeLaunch);
  const adoptBannerDismissed = useUIStore((s) => s.adoptBannerDismissedByGame[name] ?? false);
  const dismissAdoptBanner = useUIStore((s) => s.dismissAdoptBanner);
  const [adoptOpen, setAdoptOpen] = useState(false);
  useEffect(() => {
    setActiveGame(name || null);
    return () => setActiveGame(null);
  }, [name, setActiveGame]);
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
  const { data: conflictsOverview, isLoading: conflictsLoading } = useConflictsOverview(name);
  const { data: downloadJobs = [] } = useDownloadJobs(name);
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("installed");
  const [matchedSubTab, setMatchedSubTab] = useState<MatchedSubTab>("nexus-matched");
  const [selectedModId, setSelectedModId] = useState<number | null>(null);
  const [fileSelectModId, setFileSelectModId] = useState<number | null>(null);

  const modalFlow = useInstallFlow(name, archives, downloadJobs);
  const deploy = useDeploy(name || null);

  const handleFileSelect = useCallback((modId: number) => {
    setSelectedModId(modId);
    setFileSelectModId(modId);
  }, []);

  const installedModIds = useMemo(
    () => new Set(installedMods.filter((m) => m.nexus_mod_id != null).map((m) => m.nexus_mod_id!)),
    [installedMods],
  );

  const frameworksPanelRef = useRef<HTMLDivElement>(null);
  const [highlightFrameworks, setHighlightFrameworks] = useState(false);

  // Header "Frameworks" card → jump to the Installed tab, scroll the panel into
  // view, and flash a highlight ring so the card→detail link is obvious.
  const goToFrameworks = useCallback(() => {
    setTab("installed");
    setHighlightFrameworks(true);
  }, []);

  useEffect(() => {
    if (!highlightFrameworks || tab !== "installed") return;
    frameworksPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    const t = window.setTimeout(() => setHighlightFrameworks(false), 1600);
    return () => window.clearTimeout(t);
  }, [highlightFrameworks, tab]);

  const healthPanelRef = useRef<HTMLDivElement>(null);
  const [highlightHealth, setHighlightHealth] = useState(false);

  // Header "Health" card → jump to the Installed tab and flash the health panel.
  const goToHealth = useCallback(() => {
    setTab("installed");
    setHighlightHealth(true);
  }, []);

  useEffect(() => {
    if (!highlightHealth || tab !== "installed") return;
    healthPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    const t = window.setTimeout(() => setHighlightHealth(false), 1600);
    return () => window.clearTimeout(t);
  }, [highlightHealth, tab]);

  const [isLaunching, setIsLaunching] = useState(false);
  const [launchGate, setLaunchGate] = useState<HealthReport | null>(null);
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

  const runDeployAndLaunch = async () => {
    if (!game || !gameVersion?.exe_path) return;
    setIsLaunching(true);
    try {
      const report = await deploy.mutateAsync();
      if (report.preflight && !report.preflight.ok) {
        toast.error(
          "Deploy refused",
          report.preflight.reasons.join(" ") || "Pre-flight check failed",
        );
        return;
      }
      if (report.failed > 0) {
        toast.error(
          "Deploy failed",
          `${report.failed} of ${report.total} operations failed. Game not launched.`,
        );
        return;
      }
      // Block launch when REDmod compile failed — game would otherwise start with
      // stale scripts and the user wouldn't see their REDmod changes.
      if (report.redmod && report.redmod.ran && !report.redmod.success) {
        toast.error(
          "REDmod compile failed",
          `${report.redmod.error || "redmod deploy returned an error"}. Game not launched.`,
        );
        return;
      }
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

  const handleLaunch = async () => {
    if (!game || !gameVersion?.exe_path) return;
    // Pre-launch health gate: warn (but allow override) on critical issues a
    // deploy won't fix -- e.g. a missing required mod. Opt-out via Settings;
    // never blocks on error.
    if (warnBeforeLaunch) {
      try {
        const health = await api.get<HealthReport>(`/api/v1/games/${game.name}/health/`);
        if (health.critical > 0) {
          setLaunchGate(health);
          return;
        }
      } catch {
        // a health-check failure must not prevent launching
      }
    }
    await runDeployAndLaunch();
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

  const adoptableMods = useMemo(() => {
    const installedIds = new Set(
      installedMods.filter((m) => m.nexus_mod_id != null).map((m) => m.nexus_mod_id!),
    );
    return nexusMatched.filter(
      (m) => m.nexus_match && !installedIds.has(m.nexus_match.nexus_mod_id),
    );
  }, [nexusMatched, installedMods]);
  const recognizedNotInstalled = adoptableMods.length;

  const tabCounts = useMemo<Partial<Record<Tab, number>>>(() => ({
    installed: installedLoading ? undefined : installedMods.length + recognizedNotInstalled,
    matched: modsLoading ? undefined : nexusMatched.length,
    archives: archivesLoading ? undefined : archives.length,
    updates: updatesLoading ? undefined : updates?.updates_available,
    conflicts: conflictsLoading ? undefined : conflictsOverview?.mods_affected,
    profiles: profilesLoading ? undefined : profiles.length,
    trending: trendingLoading ? undefined : (trendingResult?.trending.length ?? 0) + (trendingResult?.latest_updated.length ?? 0),
    endorsed: endorsedLoading ? undefined : endorsedMods.length,
    tracked: trackedLoading ? undefined : trackedMods.length,
  }), [
    installedMods.length, installedLoading, recognizedNotInstalled,
    nexusMatched.length, modsLoading,
    archives.length, archivesLoading,
    updates?.updates_available, updatesLoading,
    conflictsOverview?.mods_affected, conflictsLoading,
    profiles.length, profilesLoading,
    trendingResult, trendingLoading,
    endorsedMods.length, endorsedLoading,
    trackedMods.length, trackedLoading,
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
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-4">
          {Array.from({ length: 7 }, (_, i) => (
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
          <Button onClick={handleLaunch} loading={isLaunching} disabled={!gameVersion?.exe_path} title="Launch the game executable">
            <Play size={16} /> Play
          </Button>
          <Button variant="secondary" onClick={handleFullScan} loading={isScanning} title="Scan game folder for mods, group files, and match them to Nexus Mods">
            <Scan size={16} /> Scan & Correlate
          </Button>
        </div>
      </div>

      {scanPhase && (
        <ScanProgress logs={scanLogs} percent={scanPercent} phase={scanPhase} />
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-4">
        <Card
          className="hover:border-success/40 transition-colors"
          onClick={() => { setTab("matched"); setMatchedSubTab("scan-details"); }}
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
          onClick={() => { setTab("matched"); setMatchedSubTab("nexus-matched"); }}
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
        <Card
          className={cn(
            "transition-colors",
            (conflictsOverview?.mods_affected ?? 0) > 0
              ? "hover:border-warning/40"
              : "hover:border-success/40",
          )}
          onClick={() => setTab("conflicts")}
          title="Installed mods with file or resource conflicts"
        >
          <div className="flex items-center gap-3">
            <AlertTriangle
              size={18}
              className={(conflictsOverview?.mods_affected ?? 0) > 0 ? "text-warning" : "text-success"}
            />
            <div>
              <p className="text-xs text-text-muted">Conflicts</p>
              <p className="text-lg font-bold text-text-primary">
                {conflictsLoading ? "--" : (conflictsOverview?.mods_affected ?? 0)}
              </p>
            </div>
          </div>
        </Card>
        <FrameworksStatCard gameName={name} onOpen={goToFrameworks} />
        <HealthStatCard gameName={name} onOpen={goToHealth} />
      </div>

      {recognizedNotInstalled > 0 && !adoptBannerDismissed && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-accent/30 bg-accent/5 p-4">
          <div className="flex items-center gap-3">
            <Package size={20} className="shrink-0 text-accent" />
            <div>
              <p className="text-sm font-medium text-text-primary">
                {recognizedNotInstalled} mod{recognizedNotInstalled === 1 ? "" : "s"} detected on disk{" "}
                {recognizedNotInstalled === 1 ? "isn't" : "aren't"} managed yet
              </p>
              <p className="text-xs text-text-muted">
                Adopt them to unlock profiles, updates, and clean uninstall — without re-downloading.
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button
              size="sm"
              onClick={() => {
                setTab("installed");
                setAdoptOpen(true);
              }}
            >
              Review &amp; adopt
            </Button>
            <button
              type="button"
              onClick={() => dismissAdoptBanner(name)}
              title="Dismiss"
              className="rounded p-1 text-text-muted hover:text-text-primary"
            >
              <X size={16} />
            </button>
          </div>
        </div>
      )}

      <div className="relative">
        {canScrollLeft && (
          <div className="pointer-events-none absolute left-0 top-0 bottom-0 w-8 z-10 bg-gradient-to-r from-surface-0 to-transparent" />
        )}
        <div
          ref={tabsRef}
          onScroll={handleTabScroll}
          className="flex gap-1 border-b border-border overflow-x-auto scrollbar-none"
        >
          {TABS.map(({ key, label, description }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              title={description}
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
              {key === "conflicts" && (conflictsOverview?.mods_affected ?? 0) > 0 && (
                <span className="h-1.5 w-1.5 rounded-full bg-danger inline-block" />
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

      {(() => {
        const active = TABS.find((t) => t.key === tab);
        if (!active) return null;
        return (
          <p className="mt-2 mb-3 text-xs text-text-muted">{active.description}</p>
        );
      })()}

      <div key={tab} className="animate-fade-in">
      {tab === "matched" && (
        <div className="space-y-4">
          <div className="flex gap-1 border-b border-border">
            {MATCHED_SUB_TABS.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setMatchedSubTab(key)}
                className={cn(
                  "px-3 py-1.5 text-sm font-medium transition-colors border-b-2 -mb-px",
                  matchedSubTab === key
                    ? "border-accent text-accent"
                    : "border-transparent text-text-muted hover:text-text-secondary",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          {matchedSubTab === "nexus-matched" && (
            <NexusMatchedGrid
              mods={nexusMatched}
              archives={archives}
              installedMods={installedMods}
              gameName={name}
              downloadJobs={downloadJobs}
              isLoading={modsLoading}
              onModClick={setSelectedModId}
              onFileSelect={handleFileSelect}
              viewModeKey="matched"
            />
          )}
          {matchedSubTab === "scan-details" && (
            <ModsTable mods={mods} gameName={name} isLoading={modsLoading} />
          )}
        </div>
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
          onFileSelect={handleFileSelect}
          hideBadges={["endorsed", "installed"]}
          viewModeKey="endorsed"
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
          onFileSelect={handleFileSelect}
          hideBadges={["tracked", "installed", "endorsed"]}
          viewModeKey="tracked"
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
          onFileSelect={handleFileSelect}
        />
      )}
      {tab === "conflicts" && (
        <ConflictSubTabs gameName={name} gameDomain={game?.domain_name ?? ""} />
      )}
      {tab === "installed" && (
        <>
          <div
            ref={healthPanelRef}
            className={cn(
              "mb-4 scroll-mt-4 rounded-xl transition-shadow duration-500",
              highlightHealth && "ring-2 ring-warning ring-offset-2 ring-offset-surface-0",
            )}
          >
            <HealthWidget gameName={name} onGoToUpdates={() => setTab("updates")} />
          </div>
          <div
            ref={frameworksPanelRef}
            className={cn(
              "mb-4 scroll-mt-4 rounded-xl transition-shadow duration-500",
              highlightFrameworks && "ring-2 ring-warning ring-offset-2 ring-offset-surface-0",
            )}
          >
            <FrameworksWidget gameName={name} />
          </div>
          <InstalledCollectionsSection gameName={name} />
          <InstalledModsTable
            mods={installedMods}
            gameName={name}
            recognizedMods={nexusMatched}
            archives={archives}
            downloadJobs={downloadJobs}
            updates={updates?.updates ?? []}
            isLoading={installedLoading}
            onModClick={setSelectedModId}
            onFileSelect={handleFileSelect}
            onTabChange={(t) => setTab(t as Tab)}
            onReviewAdopt={recognizedNotInstalled > 0 ? () => setAdoptOpen(true) : undefined}
          />
        </>
      )}
      {tab === "archives" && (
        <ArchivesList archives={archives} gameName={name} gameDomain={game.domain_name} installPath={game.install_path} isLoading={archivesLoading} onFileSelect={handleFileSelect} />
      )}
      {tab === "profiles" && (
        <ProfileManager profiles={profiles} gameName={name} isLoading={profilesLoading} installedCount={installedMods.length} recognizedCount={recognizedNotInstalled} />
      )}
      {tab === "updates" && (
        <UpdatesTable gameName={name} updates={updates?.updates ?? []} isLoading={updatesLoading} />
      )}
      </div>

      {(() => {
        const effectiveModId = selectedModId ?? modalFlow.fileSelectModId;
        if (effectiveModId == null) return null;
        const effectiveDefaultTab = fileSelectModId === effectiveModId ? "files" as const : undefined;
        const modUpdate = updateByNexusId.get(effectiveModId);
        const archive = modalFlow.archiveByModId.get(effectiveModId);
        const dl = modalFlow.completedDownloadByModId.get(effectiveModId);
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
                  completedDownload={dl}
                  archive={archive}
                  hasConflicts={modalFlow.conflicts != null}
                  isDownloading={modalFlow.downloadingModId === effectiveModId}
                  onInstall={() => archive && modalFlow.handleInstall(effectiveModId, archive)}
                  onInstallByFilename={() => {
                    if (dl) modalFlow.handleInstallByFilename(effectiveModId, dl.file_name);
                  }}
                  onDownload={() => modalFlow.handleDownload(effectiveModId)}
                  onCancelDownload={() => {
                    const activeDl = modalFlow.activeDownloadByModId.get(effectiveModId);
                    if (activeDl) modalFlow.handleCancelDownload(activeDl.id);
                  }}
                  onInstallWithPreview={
                    dl
                      ? () => modalFlow.handleInstallWithPreviewByFilename(effectiveModId, dl.file_name)
                      : archive
                        ? () => modalFlow.handleInstallWithPreview(effectiveModId, archive)
                        : undefined
                  }
                />
              )
            }
            onClose={() => {
              setSelectedModId(null);
              setFileSelectModId(null);
              modalFlow.dismissFileSelect();
            }}
          />
        );
      })()}

      {modalFlow.previewArchive && (
        <PreInstallPreview
          gameName={name}
          archiveFilename={modalFlow.previewArchive.filename}
          onConfirm={(renames) => modalFlow.confirmPreviewInstall(renames)}
          onCancel={modalFlow.dismissPreview}
        />
      )}

      {launchGate && (
        <ConfirmDialog
          title="Launch anyway?"
          message={`${launchGate.critical} critical issue${launchGate.critical !== 1 ? "s" : ""} may stop mods from working:`}
          confirmLabel="Launch anyway"
          variant="warning"
          icon={AlertTriangle}
          onConfirm={() => {
            setLaunchGate(null);
            void runDeployAndLaunch();
          }}
          onCancel={() => setLaunchGate(null)}
        >
          <div className="space-y-3">
            <ul className="max-h-32 space-y-1.5 overflow-y-auto text-xs">
              {launchGate.issues
                .filter((i) => i.severity === "critical")
                .map((i, idx) => (
                  <li key={idx} className="text-text-secondary">
                    <span className="text-danger">• </span>
                    {i.mod_name && (
                      <span className="font-medium text-text-primary">{i.mod_name}</span>
                    )}{" "}
                    {i.message}
                    {i.suggested_fix && (
                      <span className="block pl-3 text-text-muted">→ {i.suggested_fix}</span>
                    )}
                  </li>
                ))}
            </ul>
            {launchGate.warning > 0 && (
              <div>
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                  Also worth checking
                </p>
                <ul className="max-h-24 space-y-1 overflow-y-auto text-xs text-text-secondary">
                  {launchGate.issues
                    .filter((i) => i.severity === "warning")
                    .map((i, idx) => (
                      <li key={idx}>
                        <span className="text-warning">• </span>
                        {i.mod_name && (
                          <span className="font-medium text-text-primary">{i.mod_name}</span>
                        )}{" "}
                        {i.message}
                      </li>
                    ))}
                </ul>
              </div>
            )}
            <button
              type="button"
              onClick={() => {
                setLaunchGate(null);
                goToHealth();
              }}
              className="text-xs font-medium text-accent hover:underline"
            >
              Fix issues first →
            </button>
          </div>
        </ConfirmDialog>
      )}

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
      {adoptOpen && (
        <AdoptReviewDialog
          gameName={name}
          mods={adoptableMods}
          onClose={() => setAdoptOpen(false)}
        />
      )}
    </div>
  );
}
