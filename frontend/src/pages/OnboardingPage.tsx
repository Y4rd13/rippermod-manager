import { useEffect, useState } from "react";
import { useNavigate } from "react-router";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  useCompleteOnboarding,
  useConnectNexus,
  useCreateGame,
  useSaveSettings,
  useScanMods,
  useSyncNexus,
} from "@/hooks/mutations";
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

function AddGameStep({ onFinish }: { onFinish: () => void }) {
  const store = useOnboardingStore();
  const createGame = useCreateGame();
  const scanMods = useScanMods();
  const syncNexus = useSyncNexus();
  const completeOnboarding = useCompleteOnboarding();
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const handleFinish = async () => {
    if (!store.installPath.trim()) {
      setError("Install path is required");
      return;
    }

    try {
      setStatus("Creating game...");
      await createGame.mutateAsync({
        name: store.gameName,
        domain_name: "cyberpunk2077",
        install_path: store.installPath,
      });

      setStatus("Scanning local mods...");
      const scanResult = await scanMods.mutateAsync(store.gameName);

      setStatus(`Found ${scanResult.files_found} files. Syncing Nexus history...`);
      try {
        await syncNexus.mutateAsync(store.gameName);
      } catch {
        // Nexus sync is optional
      }

      setStatus("Completing setup...");
      await completeOnboarding.mutateAsync({});
      onFinish();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Setup failed");
      setStatus("");
    }
  };

  const isLoading =
    createGame.isPending ||
    scanMods.isPending ||
    syncNexus.isPending ||
    completeOnboarding.isPending;

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
      <Input
        id="install-path"
        label="Installation Path"
        placeholder="C:\\Program Files (x86)\\Steam\\steamapps\\common\\Cyberpunk 2077"
        value={store.installPath}
        onChange={(e) => {
          store.setInstallPath(e.target.value);
          setError("");
        }}
        error={error}
      />
      {status && (
        <p className="text-accent text-sm animate-pulse">{status}</p>
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
