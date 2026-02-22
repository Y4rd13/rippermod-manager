import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { open } from "@tauri-apps/plugin-dialog";
import { invoke } from "@tauri-apps/api/core";
import { CheckCircle, ExternalLink, FolderOpen, Search } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ScanProgress, type ScanLog } from "@/components/ui/ScanProgress";
import {
  useCompleteOnboarding,
  useConnectNexus,
  useCreateGame,
  useSaveSettings,
  useSyncNexus,
  useValidatePath,
} from "@/hooks/mutations";
import { useNexusSSO } from "@/hooks/use-nexus-sso";
import { api } from "@/lib/api-client";
import { parseSSE } from "@/lib/sse-parser";
import { useOnboardingStatus } from "@/hooks/queries";
import { cn } from "@/lib/utils";
import { useOnboardingStore } from "@/stores/onboarding-store";
import type { DetectedGame, PathValidation } from "@/types/api";

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

function AISetupStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
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
        <Button variant="ghost" onClick={onBack}>Back</Button>
        <Button onClick={handleSave} loading={saveSettings.isPending}>
          Continue
        </Button>
      </div>
    </div>
  );
}

function NexusSetupStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const store = useOnboardingStore();
  const connectNexus = useConnectNexus();
  const sso = useNexusSSO();
  const [error, setError] = useState("");
  const [manualValidated, setManualValidated] = useState(false);
  const [showManual, setShowManual] = useState(false);

  const ssoStartRef = useRef(0);
  const [ssoElapsed, setSsoElapsed] = useState(0);

  useEffect(() => {
    if (sso.state !== "waiting") return;
    ssoStartRef.current = Date.now();
    const timer = setInterval(() => {
      setSsoElapsed(Math.floor((Date.now() - ssoStartRef.current) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [sso.state]);

  const ssoSuccess = sso.state === "success" && sso.result !== null;
  const validated = manualValidated || ssoSuccess;
  const displayUsername = ssoSuccess
    ? sso.result!.username
    : store.nexusUsername;

  // Sync SSO username to onboarding store
  const nexusUsername = useOnboardingStore((s) => s.nexusUsername);
  const setNexusUsername = useOnboardingStore((s) => s.setNexusUsername);

  useEffect(() => {
    if (ssoSuccess && sso.result && nexusUsername !== sso.result.username) {
      setNexusUsername(sso.result.username);
    }
  }, [ssoSuccess, sso.result, nexusUsername, setNexusUsername]);

  const handleManualValidate = () => {
    if (!store.nexusKey.trim()) {
      setError("API key is required");
      return;
    }
    connectNexus.mutate(store.nexusKey, {
      onSuccess: (result) => {
        if (result.valid) {
          store.setNexusUsername(result.username);
          setManualValidated(true);
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

      {validated ? (
        <>
          <p className="text-success text-sm">
            Connected as {displayUsername}
          </p>
          <div className="flex justify-end gap-3">
            <Button variant="ghost" onClick={onBack}>Back</Button>
            <Button onClick={onNext}>Continue</Button>
          </div>
        </>
      ) : (
        <>
          <Button
            onClick={() => sso.startSSO()}
            loading={sso.state === "connecting" || sso.state === "waiting"}
            disabled={sso.state === "connecting" || sso.state === "waiting"}
            size="lg"
            className="w-full"
          >
            <ExternalLink className="h-4 w-4" />
            {sso.state === "waiting"
              ? "Waiting for authorization..."
              : "Sign in with Nexus Mods"}
          </Button>

          {sso.state === "waiting" && (
            <div className="text-center space-y-1">
              <p className="text-text-muted text-xs">
                Waiting... ({ssoElapsed}s) — Complete authorization in your browser.
                <button
                  type="button"
                  onClick={() => sso.cancel()}
                  className="ml-2 text-accent underline"
                >
                  Cancel
                </button>
              </p>
              {ssoElapsed > 120 && (
                <p className="text-warning text-xs">
                  Taking longer than expected — try again or use manual entry below.
                </p>
              )}
            </div>
          )}

          {sso.error && <p className="text-danger text-sm">{sso.error}</p>}

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-surface-1 px-2 text-text-muted">or</span>
            </div>
          </div>

          {!showManual ? (
            <button
              type="button"
              onClick={() => setShowManual(true)}
              className="text-sm text-text-muted hover:text-text-secondary underline w-full text-center"
            >
              Enter API key manually
            </button>
          ) : (
            <div className="space-y-4">
              <Input
                id="nexus-key"
                label="Nexus Mods API Key"
                type="password"
                placeholder="Your API key from nexusmods.com/users/myaccount?tab=api+access"
                value={store.nexusKey}
                onChange={(e) => {
                  store.setNexusKey(e.target.value);
                  setError("");
                  setManualValidated(false);
                }}
                error={error}
              />
              <div className="flex justify-end">
                <Button
                  onClick={handleManualValidate}
                  loading={connectNexus.isPending}
                >
                  Validate & Connect
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function AddGameStep({ onFinish, onBack }: { onFinish: () => void; onBack: () => void }) {
  const store = useOnboardingStore();
  const createGame = useCreateGame();
  const syncNexus = useSyncNexus();
  const completeOnboarding = useCompleteOnboarding();
  const validatePath = useValidatePath();
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [scanLogs, setScanLogs] = useState<ScanLog[]>([]);
  const [scanPercent, setScanPercent] = useState(0);
  const [scanPhase, setScanPhase] = useState("");
  const [detectedPaths, setDetectedPaths] = useState<DetectedGame[]>([]);
  const [isDetecting, setIsDetecting] = useState(false);
  const [validation, setValidation] = useState<PathValidation | null>(null);

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

  const handleAutoDetect = async () => {
    setIsDetecting(true);
    setError("");
    setDetectedPaths([]);
    setValidation(null);
    try {
      const paths = await invoke<DetectedGame[]>("detect_game_paths");
      if (paths.length === 1) {
        store.setInstallPath(paths[0].path);
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
    store.setInstallPath(path);
    setDetectedPaths([]);
    handleValidate(path);
  };

  const handleValidate = (path: string) => {
    validatePath.mutate(
      { install_path: path, domain_name: "cyberpunk2077" },
      {
        onSuccess: (result) => setValidation(result),
        onError: () => setValidation(null),
      },
    );
  };

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
      const controller = new AbortController();
      abortRef.current = controller;
      const response = await api.stream(
        `/api/v1/games/${store.gameName}/mods/scan-stream`,
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
      <div className="space-y-2">
        <label className="block text-sm font-medium text-text-secondary">
          Installation Path
        </label>
        <div className="flex items-center gap-2">
          <div className="flex-1 rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm truncate">
            {store.installPath ? (
              <span className="text-text-primary">{store.installPath}</span>
            ) : (
              <span className="text-text-muted">Auto-detect or browse for your game folder</span>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            disabled={isLoading || isDetecting}
            onClick={handleAutoDetect}
            loading={isDetecting}
          >
            <Search className="h-4 w-4 mr-1" />
            Auto-detect
          </Button>
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
                setDetectedPaths([]);
                setError("");
                handleValidate(selected);
              }
            }}
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

      {scanPhase && (
        <ScanProgress logs={scanLogs} percent={scanPercent} phase={scanPhase} />
      )}

      <div className="flex justify-end gap-3">
        <Button variant="ghost" onClick={onBack} disabled={isLoading}>Back</Button>
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
  const handleBack = () => store.setStep(Math.max(0, store.currentStep - 1));
  const handleFinish = () => navigate("/dashboard", { replace: true });

  return (
    <div className="flex flex-col items-center justify-center min-h-full p-8">
      <div className="w-full max-w-2xl">
        <StepIndicator current={store.currentStep} />
        {store.currentStep === 0 && <WelcomeStep onNext={handleNext} />}
        {store.currentStep === 1 && <AISetupStep onNext={handleNext} onBack={handleBack} />}
        {store.currentStep === 2 && <NexusSetupStep onNext={handleNext} onBack={handleBack} />}
        {store.currentStep === 3 && <AddGameStep onFinish={handleFinish} onBack={handleBack} />}
      </div>
    </div>
  );
}
