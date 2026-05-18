import { ArrowDownToLine, CheckCircle, Crown, ExternalLink, Eye, EyeOff, FolderOpen, Heart, LogOut, RefreshCw, RotateCcw, User } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { open as openDialog } from "@tauri-apps/plugin-dialog";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useAbstainMod, useDisconnectNexus, useEndorseMod, useTrackMod, useUntrackMod, useUpdateGame } from "@/hooks/mutations";
import { useAppUpdater } from "@/hooks/use-app-updater";
import { useDeployStatus, useUndeploy } from "@/hooks/use-deploy";
import { useNexusSSO } from "@/hooks/use-nexus-sso";
import { useGame, useGames, useModDetail, useSettings } from "@/hooks/queries";
import { reportDeployOutcome } from "@/lib/deploy-toast";
import { cn } from "@/lib/utils";
import { toast } from "@/stores/toast-store";
import { useUIStore } from "@/stores/ui-store";

function UpdateSection() {
  const {
    status,
    updateInfo,
    error,
    errorKind,
    downloadProgress,
    checkForUpdate,
    downloadAndInstall,
    restartApp,
  } = useAppUpdater();

  return (
    <div className="mt-4 space-y-2">
      {status === "available" && updateInfo && (
        <div className="rounded-lg border border-accent/30 bg-accent/5 px-3 py-2">
          <p className="text-sm font-medium text-accent">
            Version {updateInfo.version} is available
          </p>
          {updateInfo.body && (
            <p className="mt-1 text-xs text-text-muted line-clamp-3">{updateInfo.body}</p>
          )}
        </div>
      )}

      {status === "downloading" && downloadProgress != null && (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span>Downloading update...</span>
            <span>{downloadProgress}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-surface-3">
            <div
              className="h-full rounded-full bg-accent transition-all duration-300"
              style={{ width: `${downloadProgress}%` }}
            />
          </div>
        </div>
      )}

      {status === "error" && error && (
        <p className={`text-xs ${errorKind === "network" ? "text-warning" : "text-danger"}`}>{error}</p>
      )}

      {status === "up-to-date" && (
        <p className="text-xs text-success">You are on the latest version.</p>
      )}

      <div className="flex flex-wrap gap-2">
        {(status === "idle" || status === "up-to-date" || status === "error") && (
          <Button variant="secondary" size="sm" onClick={() => void checkForUpdate()}>
            <RefreshCw className="h-3.5 w-3.5" />
            Check for Updates
          </Button>
        )}

        {status === "checking" && (
          <Button variant="secondary" size="sm" loading disabled>
            Checking...
          </Button>
        )}

        {status === "available" && (
          <Button size="sm" onClick={() => void downloadAndInstall()}>
            <ArrowDownToLine className="h-3.5 w-3.5" />
            Download &amp; Install
          </Button>
        )}

        {status === "ready" && (
          <Button size="sm" onClick={() => void restartApp()}>
            <RotateCcw className="h-3.5 w-3.5" />
            Restart Now
          </Button>
        )}
      </div>
    </div>
  );
}

const RIPPERMOD_NEXUS_MOD_ID = 27781;
const RIPPERMOD_NEXUS_DOMAIN = "cyberpunk2077";
const RIPPERMOD_NEXUS_URL = `https://www.nexusmods.com/${RIPPERMOD_NEXUS_DOMAIN}/mods/${RIPPERMOD_NEXUS_MOD_ID}`;

function DeploymentCard() {
  const activeGameName = useUIStore((s) => s.activeGameName);
  const { data: games = [] } = useGames();
  // Fall back to the first game so the card is visible from Settings without
  // having to navigate through Games first. Hidden only when no games exist
  // (onboarding state).
  const gameName = activeGameName ?? games[0]?.name ?? null;
  const status = useDeployStatus(gameName);
  const undeploy = useUndeploy(gameName);
  const { data: game } = useGame(gameName ?? "");
  const updateGame = useUpdateGame();

  if (!gameName) return null;

  const handleUndeploy = () => {
    undeploy.mutate(undefined, {
      onSuccess: (report) => reportDeployOutcome(report, "Undeploy"),
      onError: (error) => toast.error("Undeploy failed", error.message),
    });
  };

  const handlePickModsDir = async () => {
    const picked = await openDialog({
      directory: true,
      multiple: false,
      title: "Choose mods staging folder",
      defaultPath: game?.resolved_mods_dir,
    });
    if (typeof picked !== "string" || picked === game?.mods_dir) return;
    updateGame.mutate({ name: gameName, data: { mods_dir: picked } });
  };

  const handleResetModsDir = () => {
    updateGame.mutate({ name: gameName, data: { mods_dir: null } });
  };

  return (
    <Card>
      <h2 className="text-lg font-semibold text-text-primary mb-4">Deployment</h2>
      <div className="space-y-4">
        <p className="text-sm text-text-secondary">
          Mods are staged in <code>downloaded_mods/</code> and linked into the game directory
          automatically when you install, toggle, or launch the game. Use{" "}
          <strong>Undeploy</strong> to remove all links and restore your game folder to vanilla
          without uninstalling mods.
        </p>
        {status.data && (
          <div className="text-xs text-text-muted font-mono">
            {status.data.linked} linked · {status.data.missing} missing · {status.data.foreign} foreign
          </div>
        )}
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="secondary"
            loading={undeploy.isPending}
            onClick={handleUndeploy}
          >
            Undeploy
          </Button>
        </div>

        <div className="border-t border-border pt-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-text-primary">Mods staging folder</span>
            {game?.mods_dir && (
              <button
                type="button"
                onClick={handleResetModsDir}
                title="Reset to default (<install>/downloaded_mods)"
                className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary"
              >
                <RotateCcw size={12} /> Reset
              </button>
            )}
          </div>
          <p className="text-xs text-text-muted">
            Where archives are extracted before being linked into the game directory. Must live on
            the same drive as your game install (NTFS hardlinks can&apos;t cross volumes).
          </p>
          <div className="flex items-center gap-2">
            <div className="flex-1 rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-xs font-mono text-text-secondary truncate" title={game?.resolved_mods_dir}>
              {game?.resolved_mods_dir ?? "—"}
            </div>
            <Button size="sm" variant="secondary" onClick={handlePickModsDir} loading={updateGame.isPending}>
              <FolderOpen size={14} /> Change…
            </Button>
          </div>
          {game?.mods_dir == null && (
            <p className="text-[11px] text-text-muted/80">Using default location.</p>
          )}
        </div>
      </div>
    </Card>
  );
}

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
          <UpdateSection />
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
  const disconnect = useDisconnectNexus();
  const sso = useNexusSSO();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false);

  useEffect(() => {
    if (sso.state === "success") {
      qc.invalidateQueries({ queryKey: ["settings"] });
    }
  }, [sso.state, qc]);

  const currentNexus = settings.find((s) => s.key === "nexus_api_key")?.value;
  const nexusUsername = settings.find((s) => s.key === "nexus_username")?.value;
  const nexusIsPremium = settings.find((s) => s.key === "nexus_is_premium")?.value === "true";

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold text-text-primary">Settings</h1>

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

      <DeploymentCard />
      <AboutCard />
    </div>
  );
}
