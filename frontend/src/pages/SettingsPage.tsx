import { CheckCircle } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { useSaveSettings } from "@/hooks/mutations";
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
  const [openaiKey, setOpenaiKey] = useState("");
  const [nexusKey, setNexusKey] = useState("");

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
    <div className="space-y-6 max-w-xl">
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
          <ApiKeyField
            id="nexus-key"
            label="Nexus Mods API Key"
            placeholder="Your Nexus API key"
            currentValue={currentNexus}
            value={nexusKey}
            onChange={setNexusKey}
          />
          <Button onClick={handleSave} loading={saveSettings.isPending}>
            Save Changes
          </Button>
        </div>
      </Card>
    </div>
  );
}
