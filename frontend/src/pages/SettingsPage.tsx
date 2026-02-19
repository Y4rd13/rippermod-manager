import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { useSaveSettings } from "@/hooks/mutations";
import { useSettings } from "@/hooks/queries";

export function SettingsPage() {
  const { data: settings = [] } = useSettings();
  const saveSettings = useSaveSettings();
  const [openaiKey, setOpenaiKey] = useState("");
  const [nexusKey, setNexusKey] = useState("");
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    const updates: Record<string, string> = {};
    if (openaiKey) updates.openai_api_key = openaiKey;
    if (nexusKey) updates.nexus_api_key = nexusKey;
    if (Object.keys(updates).length === 0) return;

    saveSettings.mutate(updates, {
      onSuccess: () => {
        setSaved(true);
        setOpenaiKey("");
        setNexusKey("");
        setTimeout(() => setSaved(false), 2000);
      },
    });
  };

  const currentOpenai = settings.find((s) => s.key === "openai_api_key")?.value;
  const currentNexus = settings.find((s) => s.key === "nexus_api_key")?.value;

  return (
    <div className="space-y-6 max-w-xl">
      <h1 className="text-2xl font-bold text-text-primary">Settings</h1>

      <Card>
        <h2 className="text-lg font-semibold text-text-primary mb-4">
          API Keys
        </h2>
        <div className="space-y-4">
          <div>
            <Input
              id="openai-key"
              label="OpenAI API Key"
              type="password"
              placeholder={currentOpenai ? "Currently set (***)" : "sk-..."}
              value={openaiKey}
              onChange={(e) => setOpenaiKey(e.target.value)}
            />
            {currentOpenai && (
              <p className="text-xs text-text-muted mt-1">Current: {currentOpenai}</p>
            )}
          </div>
          <div>
            <Input
              id="nexus-key"
              label="Nexus Mods API Key"
              type="password"
              placeholder={currentNexus ? "Currently set (***)" : "Your Nexus API key"}
              value={nexusKey}
              onChange={(e) => setNexusKey(e.target.value)}
            />
            {currentNexus && (
              <p className="text-xs text-text-muted mt-1">Current: {currentNexus}</p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={handleSave} loading={saveSettings.isPending}>
              Save Changes
            </Button>
            {saved && <span className="text-sm text-success">Saved!</span>}
          </div>
        </div>
      </Card>
    </div>
  );
}
