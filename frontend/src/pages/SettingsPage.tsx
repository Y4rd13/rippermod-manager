import { CheckCircle, ExternalLink, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Input } from "@/components/ui/Input";
import { useDisconnectNexus, useSaveSettings } from "@/hooks/mutations";
import { useNexusSSO } from "@/hooks/use-nexus-sso";
import { useSettings } from "@/hooks/queries";

function ApiKeyField({
  id,
  label,
  placeholder,
  currentValue,
  value,
  onChange,
}: {
  id: string;
  label: string;
  placeholder: string;
  currentValue?: string;
  value: string;
  onChange: (value: string) => void;
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

export function SettingsPage() {
  const { data: settings = [] } = useSettings();
  const saveSettings = useSaveSettings();
  const disconnect = useDisconnectNexus();
  const sso = useNexusSSO();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [openaiKey, setOpenaiKey] = useState("");
  const [nexusKey, setNexusKey] = useState("");
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false);

  useEffect(() => {
    if (sso.state === "success") {
      qc.invalidateQueries({ queryKey: ["settings"] });
    }
  }, [sso.state, qc]);

  const handleSave = () => {
    const updates: Record<string, string> = {};
    if (openaiKey) updates.openai_api_key = openaiKey;
    if (nexusKey) updates.nexus_api_key = nexusKey;
    if (Object.keys(updates).length === 0) return;

    saveSettings.mutate(updates, {
      onSuccess: () => {
        setOpenaiKey("");
        setNexusKey("");
      },
    });
  };

  const currentOpenai = settings.find((s) => s.key === "openai_api_key")?.value;
  const currentNexus = settings.find((s) => s.key === "nexus_api_key")?.value;

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
          />
          <div className="space-y-3">
            <ApiKeyField
              id="nexus-key"
              label="Nexus Mods API Key"
              placeholder="Your Nexus API key"
              currentValue={currentNexus}
              value={nexusKey}
              onChange={setNexusKey}
            />
            <Button
              variant="secondary"
              size="sm"
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
          <Button onClick={handleSave} loading={saveSettings.isPending}>
            Save Changes
          </Button>
        </div>
      </Card>

      {currentNexus && (
        <Card>
          <h2 className="text-lg font-semibold text-text-primary mb-4">
            Nexus Account
          </h2>
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <p className="text-sm text-text-secondary">
                Connected with key <span className="font-mono text-xs">{"•".repeat(8)}{currentNexus.slice(-4)}</span>
              </p>
            </div>
            <Button
              variant="danger"
              size="sm"
              onClick={() => setShowDisconnectConfirm(true)}
            >
              <LogOut className="h-3.5 w-3.5" />
              Disconnect
            </Button>
          </div>
          {showDisconnectConfirm && (
            <ConfirmDialog
              title="Disconnect Nexus Account"
              message="This will remove your Nexus API key and return you to the onboarding screen to reconnect. Your games and mods will be preserved."
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
        </Card>
      )}

      <Card>
        <h2 className="text-lg font-semibold text-text-primary mb-4">
          About
        </h2>
        <div className="space-y-2 text-sm text-text-secondary">
          <p>Chat Nexus Mod Manager v0.1.0</p>
          <p>AI-powered mod manager for PC games.</p>
        </div>
      </Card>
    </div>
  );
}
