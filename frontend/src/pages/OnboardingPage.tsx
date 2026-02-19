import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { open } from "@tauri-apps/plugin-dialog";
import { ChevronDown, FolderOpen } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  useCompleteOnboarding,
  useConnectNexus,
  useCreateGame,
  useSaveSettings,
  useSyncNexus,
} from "@/hooks/mutations";
import { api } from "@/lib/api-client";
import { parseSSE } from "@/lib/sse-parser";
import { useOnboardingStatus } from "@/hooks/queries";
import { cn } from "@/lib/utils";
import { useOnboardingStore } from "@/stores/onboarding-store";

const STEPS = ["Welcome", "AI Setup", "Nexus Mods", "Add Game"];

function StepIndicator({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-2 mb-8">
      {STEPS.map((label, i) => (
        <div key={label} className="flex items-center gap-2">
          <div
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition-colors",
              i < current
                ? "bg-success text-white"
                : i === current
                  ? "bg-accent text-white"
                  : "bg-surface-3 text-text-muted",
            )}
          >
            {i < current ? "\u2713" : i + 1}
          </div>
          <span
            className={cn(
              "text-sm hidden sm:block",
              i === current ? "text-text-primary font-medium" : "text-text-muted",
            )}
          >
            {label}
          </span>
          {i < STEPS.length - 1 && (
            <div
              className={cn(
                "h-px w-8",
                i < current ? "bg-success" : "bg-border",
              )}
            />
          )}
        </div>
      ))}
    </div>
  );
}

function WelcomeStep({ onNext }: { onNext: () => void }) {
  return (
    <div className="text-center space-y-6">
      <h2 className="text-3xl font-bold text-text-primary">
        Chat Nexus Mod Manager
      </h2>
      <p className="text-text-secondary max-w-md mx-auto">
        Manage your mods with AI-powered assistance. Connect your Nexus Mods
        account, scan your local mods, and let AI help you keep everything
        organized and up to date.
      </p>
      <Button onClick={onNext} size="lg">
        Get Started
      </Button>
    </div>
  );
}

function AISetupStep({ onNext }: { onNext: () => void }) {
  const store = useOnboardingStore();
  const saveSettings = useSaveSettings();
  const [error, setError] = useState("");

  const handleSave = () => {
    if (!store.openaiKey.trim()) {
      setError("API key is required");
      return;
    }
    saveSettings.mutate(
      { openai_api_key: store.openaiKey },
      {
        onSuccess: () => onNext(),
        onError: (e) => setError(e.message),
      },
    );
  };

  return (
    <div className="space-y-6 max-w-md mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-text-primary mb-2">
          AI Configuration
        </h2>
        <p className="text-text-secondary text-sm">
          Enter your OpenAI API key to enable the chat assistant.
        </p>
      </div>
      <Input
        id="openai-key"
        label="OpenAI API Key"
        type="password"
        placeholder="sk-..."
        value={store.openaiKey}
        onChange={(e) => {
          store.setOpenaiKey(e.target.value);
          setError("");
        }}
        error={error}
      />
      <div className="flex justify-end gap-3">
        <Button onClick={handleSave} loading={saveSettings.isPending}>
          Continue
        </Button>
      </div>
    </div>
  );
}

function NexusSetupStep({ onNext }: { onNext: () => void }) {
  const store = useOnboardingStore();
  const connectNexus = useConnectNexus();
  const [error, setError] = useState("");
  const [validated, setValidated] = useState(false);

  const handleValidate = () => {
    if (!store.nexusKey.trim()) {
      setError("API key is required");
      return;
    }
    connectNexus.mutate(store.nexusKey, {
      onSuccess: (result) => {
        if (result.valid) {
          store.setNexusUsername(result.username);
          setValidated(true);
          setError("");
        } else {
          setError(result.error || "Invalid API key");
        }
      },
      onError: (e) => setError(e.message),
    });
  };

  return (
    <div className="space-y-6 max-w-md mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-text-primary mb-2">
          Nexus Mods
        </h2>
        <p className="text-text-secondary text-sm">
          Connect your Nexus Mods account to sync your mod history.
        </p>
      </div>
      <Input
        id="nexus-key"
        label="Nexus Mods API Key"
        type="password"
        placeholder="Your API key from nexusmods.com/users/myaccount?tab=api+access"
        value={store.nexusKey}
        onChange={(e) => {
          store.setNexusKey(e.target.value);
          setError("");
          setValidated(false);
        }}
        error={error}
      />
      {validated && (
        <p className="text-success text-sm">
          Connected as {store.nexusUsername}
        </p>
      )}
      <div className="flex justify-end gap-3">
        {!validated ? (
          <Button onClick={handleValidate} loading={connectNexus.isPending}>
            Validate & Connect
          </Button>
        ) : (
          <Button onClick={onNext}>Continue</Button>
        )}
      </div>
    </div>
  );
}

interface ScanLog {
  phase: string;
  message: string;
  percent: number;
}

function ScanProgress({ logs, percent, phase }: { logs: ScanLog[]; percent: number; phase: string }) {
  const [expanded, setExpanded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (expanded && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs.length, expanded]);

  const phaseLabel: Record<string, string> = {
    scan: "Scanning files",
    group: "Grouping mods",
    index: "Indexing",
    done: "Complete",
    error: "Error",
    sync: "Syncing Nexus",
    complete: "Finishing",
  };

  const isDone = phase === "done" || phase === "complete";

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-text-secondary font-medium">
            {phaseLabel[phase] ?? phase}
          </span>
          <span className="text-text-muted tabular-nums">{percent}%</span>
        </div>
        <div className="h-1.5 w-full rounded-full bg-surface-3 overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-300 ease-out",
              isDone ? "bg-success" : "bg-accent",
            )}
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      {logs.length > 0 && (
        <div className="rounded-lg border border-border bg-surface-1 overflow-hidden">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="flex w-full items-center justify-between px-3 py-2 text-xs text-text-muted hover:text-text-secondary transition-colors"
          >
            <span>{logs.length} log entries</span>
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 transition-transform duration-200",
                expanded && "rotate-180",
              )}
            />
          </button>
          <div
            className={cn(
              "overflow-hidden transition-all duration-200 ease-out",
              expanded ? "max-h-48" : "max-h-0",
            )}
          >
            <div ref={scrollRef} className="overflow-y-auto max-h-48 border-t border-border">
              {logs.slice(-50).map((log, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 px-3 py-1 text-[11px] font-mono leading-relaxed"
                >
                  <span
                    className={cn(
                      "shrink-0 mt-0.5 h-1.5 w-1.5 rounded-full",
                      log.phase === "error"
                        ? "bg-danger"
                        : log.phase === "done"
                          ? "bg-success"
                          : "bg-accent/60",
                    )}
                  />
                  <span className="text-text-muted break-all">{log.message}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function AddGameStep({ onFinish }: { onFinish: () => void }) {
  const store = useOnboardingStore();
  const createGame = useCreateGame();
  const syncNexus = useSyncNexus();
  const completeOnboarding = useCompleteOnboarding();
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [scanLogs, setScanLogs] = useState<ScanLog[]>([]);
  const [scanPercent, setScanPercent] = useState(0);
  const [scanPhase, setScanPhase] = useState("");

  const pendingLogs = useRef<ScanLog[]>([]);
  const latestPercent = useRef(0);
  const latestPhase = useRef("");
  const flushTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

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
    };
  }, []);

  const handleFinish = async () => {
    if (!store.installPath.trim()) {
      setError("Install path is required");
      return;
    }

    setIsLoading(true);
    setError("");
    setScanLogs([]);
    setScanPercent(0);
    setScanPhase("scan");
    pendingLogs.current = [];
    latestPercent.current = 0;
    latestPhase.current = "scan";

    try {
      pushLog({ phase: "scan", message: "Creating game...", percent: 0 });
      startFlushing();

      await createGame.mutateAsync({
        name: store.gameName,
        domain_name: "cyberpunk2077",
        install_path: store.installPath,
      });

      pushLog({ phase: "scan", message: "Starting mod scan...", percent: 0 });
      const response = await api.stream(
        `/api/v1/games/${store.gameName}/mods/scan-stream`,
      );

      if (!response.ok) {
        throw new Error("Scan request failed");
      }

      for await (const event of parseSSE(response)) {
        const data = JSON.parse(event.data) as ScanLog;
        pushLog(data);
      }

      pushLog({ phase: "sync", message: "Syncing Nexus history...", percent: 100 });
      latestPhase.current = "sync";
      latestPercent.current = 100;

      try {
        await syncNexus.mutateAsync(store.gameName);
        pushLog({ phase: "sync", message: "Nexus sync complete", percent: 100 });
      } catch {
        pushLog({ phase: "sync", message: "Nexus sync skipped (optional)", percent: 100 });
      }

      pushLog({ phase: "complete", message: "Completing setup...", percent: 100 });
      latestPhase.current = "complete";
      await completeOnboarding.mutateAsync({});

      stopFlushing();
      setScanPhase("done");
      setScanPercent(100);
      onFinish();
    } catch (e) {
      stopFlushing();
      setError(e instanceof Error ? e.message : "Setup failed");
      setScanPhase("error");
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-md mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-text-primary mb-2">
          Add Your Game
        </h2>
        <p className="text-text-secondary text-sm">
          Point CNMM to your game installation directory.
        </p>
      </div>
      <Input
        id="game-name"
        label="Game"
        value={store.gameName}
        onChange={(e) => store.setGameName(e.target.value)}
        disabled
      />
      <div className="space-y-1">
        <label className="block text-sm font-medium text-text-secondary">
          Installation Path
        </label>
        <div className="flex items-center gap-2">
          <div className="flex-1 rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-text-primary truncate">
            {store.installPath}
          </div>
          <Button
            variant="ghost"
            size="sm"
            disabled={isLoading}
            onClick={async () => {
              const selected = await open({
                directory: true,
                title: "Select game installation folder",
                defaultPath: store.installPath,
              });
              if (selected) {
                store.setInstallPath(selected);
                setError("");
              }
            }}
          >
            <FolderOpen className="h-4 w-4 mr-1" />
            Browse
          </Button>
        </div>
        {error && <p className="text-danger text-sm">{error}</p>}
      </div>

      {scanPhase && (
        <ScanProgress logs={scanLogs} percent={scanPercent} phase={scanPhase} />
      )}

      <div className="flex justify-end gap-3">
        <Button onClick={handleFinish} loading={isLoading}>
          Finish Setup
        </Button>
      </div>
    </div>
  );
}

export function OnboardingPage() {
  const navigate = useNavigate();
  const { data: onboardingStatus } = useOnboardingStatus();
  const store = useOnboardingStore();

  useEffect(() => {
    if (onboardingStatus?.completed) {
      navigate("/dashboard", { replace: true });
    }
  }, [onboardingStatus?.completed, navigate]);

  const handleNext = () => store.setStep(store.currentStep + 1);
  const handleFinish = () => navigate("/dashboard", { replace: true });

  return (
    <div className="flex flex-col items-center justify-center min-h-full p-8">
      <div className="w-full max-w-2xl">
        <StepIndicator current={store.currentStep} />
        {store.currentStep === 0 && <WelcomeStep onNext={handleNext} />}
        {store.currentStep === 1 && <AISetupStep onNext={handleNext} />}
        {store.currentStep === 2 && <NexusSetupStep onNext={handleNext} />}
        {store.currentStep === 3 && <AddGameStep onFinish={handleFinish} />}
      </div>
    </div>
  );
}
