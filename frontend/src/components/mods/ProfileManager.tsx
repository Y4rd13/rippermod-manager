import {
  Download,
  FolderOpen,
  Plus,
  Save,
  Trash2,
  Upload,
} from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import {
  useDeleteProfile,
  useExportProfile,
  useImportProfile,
  useLoadProfile,
  useSaveProfile,
} from "@/hooks/mutations";
import type { ProfileExport, ProfileOut } from "@/types/api";

interface Props {
  profiles: ProfileOut[];
  gameName: string;
}

export function ProfileManager({ profiles, gameName }: Props) {
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [importError, setImportError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const saveProfile = useSaveProfile();
  const loadProfile = useLoadProfile();
  const deleteProfile = useDeleteProfile();
  const exportProfile = useExportProfile();
  const importProfile = useImportProfile();

  const handleCreate = () => {
    if (!newName.trim()) return;
    saveProfile.mutate(
      { gameName, name: newName.trim() },
      {
        onSuccess: () => {
          setNewName("");
          setShowCreate(false);
        },
      },
    );
  };

  const handleExport = async (profileId: number) => {
    const data = await exportProfile.mutateAsync({ gameName, profileId });
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${data.profile_name}_modlist.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setImportError("");
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const data = JSON.parse(reader.result as string) as ProfileExport;
          importProfile.mutate({ gameName, data });
        } catch {
          setImportError("Invalid profile file: could not parse JSON.");
        }
      };
      reader.readAsText(file);
      e.target.value = "";
    },
    [gameName, importProfile],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-text-secondary">
          Saved Profiles
        </h3>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload size={14} /> Import
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            className="hidden"
            onChange={handleImport}
          />
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus size={14} /> Save Current
          </Button>
        </div>
      </div>

      {showCreate && (
        <Card>
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <Input
                id="profile-name"
                label="Profile Name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Performance, Visuals, Full Setup"
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              />
            </div>
            <Button
              size="sm"
              loading={saveProfile.isPending}
              onClick={handleCreate}
            >
              <Save size={14} /> Save
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowCreate(false)}
            >
              Cancel
            </Button>
          </div>
        </Card>
      )}

      {importError && (
        <p className="text-sm text-danger">{importError}</p>
      )}

      {profiles.length === 0 && !showCreate ? (
        <p className="py-4 text-sm text-text-muted">
          No profiles saved. Save your current mod setup as a profile.
        </p>
      ) : (
        <div className="space-y-2">
          {profiles.map((p) => (
            <Card key={p.id}>
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-text-primary">{p.name}</p>
                  <p className="text-xs text-text-muted">
                    {p.mod_count} mods &middot;{" "}
                    {new Date(p.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={
                      loadProfile.isPending &&
                      loadProfile.variables?.profileId === p.id
                    }
                    onClick={() =>
                      loadProfile.mutate({ gameName, profileId: p.id })
                    }
                  >
                    <FolderOpen size={14} className="text-accent" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={
                      exportProfile.isPending &&
                      exportProfile.variables?.profileId === p.id
                    }
                    onClick={() => handleExport(p.id)}
                  >
                    <Download size={14} className="text-text-muted" />
                  </Button>
                  {confirmDelete === p.id ? (
                    <Button
                      variant="danger"
                      size="sm"
                      loading={
                        deleteProfile.isPending &&
                        deleteProfile.variables?.profileId === p.id
                      }
                      onClick={() => {
                        deleteProfile.mutate({ gameName, profileId: p.id });
                        setConfirmDelete(null);
                      }}
                    >
                      Confirm
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setConfirmDelete(p.id)}
                    >
                      <Trash2 size={14} className="text-danger" />
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
