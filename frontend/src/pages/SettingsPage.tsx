import { CheckCircle, Crown, ExternalLink, Eye, EyeOff, Heart, LogOut, User } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Input } from "@/components/ui/Input";
import { useAbstainMod, useDisconnectNexus, useEndorseMod, useSaveSettings, useTrackMod, useUntrackMod } from "@/hooks/mutations";
import { useNexusSSO } from "@/hooks/use-nexus-sso";
import { useGames, useModDetail, useSettings } from "@/hooks/queries";
import { cn } from "@/lib/utils";

function ApiKeyField({
  id,
  label,
  placeholder,
  currentValue,
  value,
  onChange,
  hint,
}: {
  id: string;
  label: string;
  placeholder: string;
  currentValue?: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
}) {
  return (
    <div className="space-y-2">
      <Input
        id={id}
        label={label}
        type="password"
        placeholder={currentValue ? "Enter new key to replace" : placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && <p className="text-xs text-text-muted">{hint}</p>}
      {currentValue && (
        <div className="flex items-center gap-2 rounded-md bg-surface-2 px-3 py-2">
          <CheckCircle size={14} className="shrink-0 text-success" />
          <span className="min-w-0 flex-1 truncate font-mono text-xs text-text-secondary">
            {currentValue}
          </span>
        </div>
      )}
    </div>
  );
}

const RIPPERMOD_NEXUS_MOD_ID = 27781;
const RIPPERMOD_NEXUS_DOMAIN = "cyberpunk2077";
const RIPPERMOD_NEXUS_URL = `https://www.nexusmods.com/${RIPPERMOD_NEXUS_DOMAIN}/mods/${RIPPERMOD_NEXUS_MOD_ID}`;

function AboutCard() {
  const { data: games = [] } = useGames();
  const gameName = games[0]?.name;
  const { data: detail } = useModDetail(
    RIPPERMOD_NEXUS_DOMAIN,
    RIPPERMOD_NEXUS_MOD_ID > 0 ? RIPPERMOD_NEXUS_MOD_ID : null,
  );

  const endorseMod = useEndorseMod();
  const abstainMod = useAbstainMod();
  const trackMod = useTrackMod();
  const untrackMod = useUntrackMod();

  const isEndorsed = detail?.is_endorsed ?? false;
  const isTracked = detail?.is_tracked ?? false;
  const endorsePending = endorseMod.isPending || abstainMod.isPending;
  const trackPending = trackMod.isPending || untrackMod.isPending;

  const canInteract = !!gameName && RIPPERMOD_NEXUS_MOD_ID > 0;

  return (
    <Card>
      <div className="flex items-start gap-4">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-accent/20 to-accent/5 text-accent">
          <span className="text-xl font-bold leading-none">R</span>
        </div>
        <div className="min-w-0 flex-1 space-y-1">
          <h2 className="text-lg font-semibold text-text-primary">RipperMod Manager</h2>
          <p className="text-text-muted text-xs font-mono">{__APP_VERSION__}</p>
        </div>
      </div>

      {canInteract && (
        <>
          <div className="mt-5 rounded-lg border border-border/60 bg-surface-0 p-4">
            <p className="text-sm text-text-secondary mb-3">
              Enjoying RipperMod Manager? Show your support on Nexus Mods!
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={endorsePending}
                onClick={() => {
                  if (!gameName) return;
                  if (isEndorsed) abstainMod.mutate({ gameName, modId: RIPPERMOD_NEXUS_MOD_ID });
                  else endorseMod.mutate({ gameName, modId: RIPPERMOD_NEXUS_MOD_ID });
                }}
                className={cn(
                  "inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-all",
                  "disabled:opacity-50",
                  isEndorsed
                    ? "border-danger/30 bg-danger/10 text-danger hover:bg-danger/15"
                    : "border-border bg-surface-2 text-text-secondary hover:border-danger/40 hover:text-danger",
                )}
              >
                {endorsePending ? (
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <Heart size={16} fill={isEndorsed ? "currentColor" : "none"} />
                )}
                {isEndorsed ? "Endorsed" : "Endorse"}
              </button>

              <button
                type="button"
                disabled={trackPending}
                onClick={() => {
                  if (!gameName) return;
                  if (isTracked) untrackMod.mutate({ gameName, modId: RIPPERMOD_NEXUS_MOD_ID });
                  else trackMod.mutate({ gameName, modId: RIPPERMOD_NEXUS_MOD_ID });
                }}
                className={cn(
                  "inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-all",
                  "disabled:opacity-50",
                  isTracked
                    ? "border-accent/30 bg-accent/10 text-accent hover:bg-accent/15"
                    : "border-border bg-surface-2 text-text-secondary hover:border-accent/40 hover:text-accent",
                )}
              >
                {trackPending ? (
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : isTracked ? (
                  <EyeOff size={16} />
                ) : (
                  <Eye size={16} />
                )}
                {isTracked ? "Tracked" : "Track"}
              </button>

              <a
                href={RIPPERMOD_NEXUS_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-2 px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:border-text-muted hover:text-text-primary"
              >
                <ExternalLink size={14} />
                View on Nexus
              </a>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}

export function SettingsPage() {
  const { data: settings = [] } = useSettings();
  const saveSettings = useSaveSettings();
  const disconnect = useDisconnectNexus();
  const sso = useNexusSSO();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [openaiKey, setOpenaiKey] = useState("");
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false);

  const savedAiModel = settings.find((s) => s.key === "ai_search_model")?.value ?? "gpt-5-mini";
  const savedAiEffort = settings.find((s) => s.key === "ai_search_effort")?.value ?? "low";
  const [aiModel, setAiModel] = useState<string | null>(null);
  const [aiEffort, setAiEffort] = useState<string | null>(null);
  const currentAiModel = aiModel ?? savedAiModel;
  const currentAiEffort = aiEffort ?? savedAiEffort;
  const aiDirty = currentAiModel !== savedAiModel || currentAiEffort !== savedAiEffort;

  useEffect(() => {
    if (sso.state === "success") {
      qc.invalidateQueries({ queryKey: ["settings"] });
    }
  }, [sso.state, qc]);

  const handleSave = () => {
    if (!openaiKey) return;
    saveSettings.mutate(
      { openai_api_key: openaiKey },
      { onSuccess: () => setOpenaiKey("") },
    );
  };

  const currentOpenai = settings.find((s) => s.key === "openai_api_key")?.value;
  const currentNexus = settings.find((s) => s.key === "nexus_api_key")?.value;
  const nexusUsername = settings.find((s) => s.key === "nexus_username")?.value;
  const nexusIsPremium = settings.find((s) => s.key === "nexus_is_premium")?.value === "true";

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold text-text-primary">Settings</h1>

      <Card>
        <h2 className="text-lg font-semibold text-text-primary mb-4">
          API Keys
        </h2>
        <div className="space-y-4">
          <ApiKeyField
            id="openai-key"
            label="OpenAI API Key"
            placeholder="sk-..."
            currentValue={currentOpenai}
            value={openaiKey}
            onChange={setOpenaiKey}
            hint="Required for AI Search and the chat agent. Get one at platform.openai.com."
          />
          <Button onClick={handleSave} loading={saveSettings.isPending} disabled={!openaiKey}>
            Save Changes
          </Button>
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold text-text-primary mb-4">
          AI Search
        </h2>
        <p className="text-xs text-text-muted mb-4">
          Configure the OpenAI model used when AI Search is enabled during scans.
        </p>
        <div className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-text-secondary">Model</label>
            <div className="grid grid-cols-2 gap-3">
              {([
                { value: "gpt-5-mini", label: "gpt-5-mini", desc: "Cost-optimized", tip: "Faster and cheaper — good for most mod matching tasks" },
                { value: "gpt-5.2", label: "gpt-5.2", desc: "Best quality", tip: "More accurate but slower and more expensive" },
              ] as const).map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  title={opt.tip}
                  onClick={() => setAiModel(opt.value)}
                  className={cn(
                    "rounded-lg border px-4 py-3 text-left transition-colors",
                    currentAiModel === opt.value
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-border bg-surface-2 text-text-muted hover:border-text-muted",
                  )}
                >
                  <p className="text-sm font-medium">{opt.label}</p>
                  <p className="text-xs opacity-70">{opt.desc}</p>
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-text-secondary">Reasoning Effort</label>
            <div className="flex gap-2">
              {([
                { value: "low", tip: "Fastest — uses minimal reasoning tokens" },
                { value: "medium", tip: "Balanced speed and accuracy" },
                { value: "high", tip: "Most thorough — uses more tokens and takes longer" },
              ] as const).map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  title={opt.tip}
                  onClick={() => setAiEffort(opt.value)}
                  className={cn(
                    "rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
                    currentAiEffort === opt.value
                      ? "bg-accent text-white"
                      : "bg-surface-2 text-text-muted hover:text-text-secondary",
                  )}
                >
                  {opt.value}
                </button>
              ))}
            </div>
          </div>
          <Button
            onClick={() => {
              saveSettings.mutate(
                { ai_search_model: currentAiModel, ai_search_effort: currentAiEffort },
                { onSuccess: () => { setAiModel(null); setAiEffort(null); } },
              );
            }}
            loading={saveSettings.isPending}
            disabled={!aiDirty}
          >
            Save Changes
          </Button>
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold text-text-primary mb-4">
          Nexus Account
        </h2>
        {currentNexus ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-success/15">
                  <User size={18} className="text-success" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-text-primary">
                      {nexusUsername || "Connected"}
                    </p>
                    {nexusIsPremium && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-warning/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-warning">
                        <Crown size={10} />
                        Premium
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-text-muted">
                    <CheckCircle size={12} className="text-success" />
                    Nexus Mods account linked
                  </div>
                </div>
              </div>
              <Button
                variant="danger"
                size="sm"
                title="Disconnect your Nexus Mods account from RipperMod Manager"
                onClick={() => setShowDisconnectConfirm(true)}
              >
                <LogOut className="h-3.5 w-3.5" />
                Disconnect
              </Button>
            </div>
            {showDisconnectConfirm && (
              <ConfirmDialog
                title="Disconnect Nexus Account"
                message="This will disconnect your Nexus Mods account and return you to the onboarding screen to reconnect. Your games and mods will be preserved."
                confirmLabel="Disconnect"
                icon={LogOut}
                loading={disconnect.isPending}
                onConfirm={() =>
                  disconnect.mutate(undefined, {
                    onSuccess: () => navigate("/onboarding", { replace: true }),
                  })
                }
                onCancel={() => setShowDisconnectConfirm(false)}
              />
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-text-secondary">
              Sign in with your Nexus Mods account to sync mod history.
            </p>
            <Button
              variant="secondary"
              title="Opens Nexus Mods in your browser for SSO authentication"
              onClick={() => sso.startSSO()}
              loading={sso.state === "connecting" || sso.state === "waiting"}
              disabled={sso.state === "connecting" || sso.state === "waiting"}
            >
              <ExternalLink className="h-3.5 w-3.5" />
              {sso.state === "waiting"
                ? "Waiting for authorization..."
                : "Sign in with Nexus Mods"}
            </Button>
            {sso.state === "waiting" && (
              <p className="text-text-muted text-xs">
                Complete authorization in your browser.{" "}
                <button
                  type="button"
                  onClick={() => sso.cancel()}
                  className="text-accent underline"
                >
                  Cancel
                </button>
              </p>
            )}
            {sso.state === "success" && sso.result && (
              <p className="text-success text-xs">
                Connected as {sso.result.username}
              </p>
            )}
            {sso.error && <p className="text-danger text-xs">{sso.error}</p>}
          </div>
        )}
      </Card>

      <AboutCard />
    </div>
  );
}
