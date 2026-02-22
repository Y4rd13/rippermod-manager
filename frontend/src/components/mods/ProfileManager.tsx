import {
  AlertTriangle,
  Check,
  Copy,
  Download,
  FolderOpen,
  GitCompare,
  Info,
  Pencil,
  Plus,
  Save,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { ProfileCompareDialog } from "@/components/mods/ProfileCompareDialog";
import { ProfileDiffDialog } from "@/components/mods/ProfileDiffDialog";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ContextMenu, type ContextMenuItem } from "@/components/ui/ContextMenu";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import {
  useCompareProfiles,
  useDeleteProfile,
  useDuplicateProfile,
  useExportProfile,
  useImportProfile,
  useLoadProfile,
  usePreviewProfile,
  useSaveProfile,
  useUpdateProfile,
} from "@/hooks/mutations";
import { useContextMenu } from "@/hooks/use-context-menu";
import { isoToEpoch, timeAgo } from "@/lib/format";
import type { ProfileCompareOut, ProfileDiffOut, ProfileExport, ProfileOut } from "@/types/api";

function CreateProfileForm({
  installedCount,
  recognizedCount,
  isPending,
  onSave,
  onCancel,
}: {
  installedCount: number;
  recognizedCount: number;
  isPending: boolean;
  onSave: (name: string, description: string) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const handleCreate = () => {
    if (!name.trim()) return;
    onSave(name.trim(), description.trim());
  };

  return (
    <Card>
      <div className="space-y-3">
        {installedCount === 0 && recognizedCount > 0 && (
          <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2">
            <AlertTriangle size={14} className="text-warning mt-0.5 shrink-0" />
            <p className="text-xs text-text-secondary">
              You have <strong>{recognizedCount} recognized mods</strong> but no managed mods yet.
              Profiles only snapshot mods that have been <strong>installed through the manager</strong>.
              Go to the Installed tab and install your recognized mods first, then save a profile.
            </p>
          </div>
        )}
        {installedCount === 0 && recognizedCount === 0 && (
          <div className="flex items-start gap-2 rounded-lg border border-border bg-surface-2/50 px-3 py-2">
            <Info size={14} className="text-text-muted mt-0.5 shrink-0" />
            <p className="text-xs text-text-secondary">
              No mods installed yet. Run a scan first to discover mods, then install them to create a profile.
            </p>
          </div>
        )}
        {installedCount > 0 && (
          <div className="flex items-start gap-2 rounded-lg border border-border bg-surface-2/50 px-3 py-2">
            <Info size={14} className="text-text-muted mt-0.5 shrink-0" />
            <p className="text-xs text-text-secondary">
              This will snapshot your <strong>{installedCount} managed mod{installedCount !== 1 ? "s" : ""}</strong> and their enabled/disabled states.
            </p>
          </div>
        )}
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <Input
              id="profile-name"
              label="Profile Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Performance, Visuals, Full Setup"
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            />
          </div>
          <Button
            size="sm"
            loading={isPending}
            onClick={handleCreate}
            disabled={installedCount === 0}
            title={installedCount === 0 ? "No managed mods to save — install mods first" : "Save current mod state as a profile"}
          >
            <Save size={14} /> Save
          </Button>
          <Button variant="secondary" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        </div>
        <textarea
          className="w-full rounded-lg border border-border bg-surface-0 px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:border-accent focus:outline-none"
          rows={2}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Optional description or notes..."
        />
      </div>
    </Card>
  );
}

const CONTEXT_MENU_ITEMS: ContextMenuItem[] = [
  { key: "load", label: "Load", icon: FolderOpen },
  { key: "export", label: "Export", icon: Download },
  { key: "rename", label: "Rename", icon: Pencil },
  { key: "duplicate", label: "Duplicate", icon: Copy },
  { key: "separator", label: "", separator: true },
  { key: "delete", label: "Delete", icon: Trash2, variant: "danger" },
];

interface Props {
  profiles: ProfileOut[];
  gameName: string;
  isLoading?: boolean;
  installedCount?: number;
  recognizedCount?: number;
}

export function ProfileManager({ profiles, gameName, isLoading = false, installedCount = 0, recognizedCount = 0 }: Props) {
  const [showCreate, setShowCreate] = useState(false);
  const [importError, setImportError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Diff/Preview state
  const [diffPreview, setDiffPreview] = useState<ProfileDiffOut | null>(null);
  const [diffProfileId, setDiffProfileId] = useState<number | null>(null);

  // Compare state
  const [compareMode, setCompareMode] = useState(false);
  const [selectedForCompare, setSelectedForCompare] = useState<number[]>([]);
  const [compareResult, setCompareResult] = useState<ProfileCompareOut | null>(null);

  // Inline rename state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");

  // Duplicate state
  const [duplicateId, setDuplicateId] = useState<number | null>(null);
  const [duplicateName, setDuplicateName] = useState("");

  // Drag & drop state
  const [isDragOver, setIsDragOver] = useState(false);

  const saveProfile = useSaveProfile();
  const loadProfile = useLoadProfile();
  const deleteProfile = useDeleteProfile();
  const exportProfile = useExportProfile();
  const importProfile = useImportProfile();
  const previewProfile = usePreviewProfile();
  const updateProfile = useUpdateProfile();
  const duplicateProfile = useDuplicateProfile();
  const compareProfiles = useCompareProfiles();

  const { menuState, openMenu, closeMenu } = useContextMenu<ProfileOut>();

  const handleCreate = (name: string, description: string) => {
    saveProfile.mutate(
      { gameName, name, description },
      { onSuccess: () => setShowCreate(false) },
    );
  };

  const handleLoadWithPreview = async (profileId: number) => {
    try {
      const diff = await previewProfile.mutateAsync({ gameName, profileId });
      setDiffPreview(diff);
      setDiffProfileId(profileId);
    } catch {
      // Error state handled by React Query
    }
  };

  const handleConfirmLoad = () => {
    if (diffProfileId == null) return;
    loadProfile.mutate(
      { gameName, profileId: diffProfileId },
      {
        onSettled: () => {
          setDiffPreview(null);
          setDiffProfileId(null);
        },
      },
    );
  };

  const handleExport = async (profileId: number) => {
    try {
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
    } catch {
      // Error state handled by React Query
    }
  };

  const handleImportData = useCallback(
    (data: ProfileExport) => {
      importProfile.mutate({ gameName, data });
    },
    [gameName, importProfile],
  );

  const handleImport = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setImportError("");
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const data = JSON.parse(reader.result as string) as ProfileExport;
          handleImportData(data);
        } catch {
          setImportError("Invalid profile file: could not parse JSON.");
        }
      };
      reader.readAsText(file);
      e.target.value = "";
    },
    [handleImportData],
  );

  const handleRename = (profile: ProfileOut) => {
    setEditingId(profile.id);
    setEditName(profile.name);
    setEditDescription(profile.description);
  };

  const handleSaveRename = () => {
    if (editingId == null || !editName.trim()) return;
    updateProfile.mutate(
      {
        gameName,
        profileId: editingId,
        data: { name: editName.trim(), description: editDescription.trim() },
      },
      { onSuccess: () => setEditingId(null) },
    );
  };

  const handleDuplicate = (profile: ProfileOut) => {
    setDuplicateId(profile.id);
    setDuplicateName(`${profile.name} (copy)`);
  };

  const handleSaveDuplicate = () => {
    if (duplicateId == null || !duplicateName.trim()) return;
    duplicateProfile.mutate(
      { gameName, profileId: duplicateId, name: duplicateName.trim() },
      { onSuccess: () => setDuplicateId(null) },
    );
  };

  const handleCompareToggle = (profileId: number) => {
    setSelectedForCompare((prev) =>
      prev.includes(profileId)
        ? prev.filter((id) => id !== profileId)
        : prev.length < 2
          ? [...prev, profileId]
          : prev,
    );
  };

  const handleCompare = async () => {
    if (selectedForCompare.length !== 2) return;
    try {
      const result = await compareProfiles.mutateAsync({
        gameName,
        data: {
          profile_id_a: selectedForCompare[0]!,
          profile_id_b: selectedForCompare[1]!,
        },
      });
      setCompareResult(result);
    } catch {
      // Error state handled by React Query
    }
  };

  // Drag & drop handlers
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      setImportError("");
      const file = e.dataTransfer.files[0];
      if (!file || !file.name.endsWith(".json")) {
        setImportError("Please drop a .json profile file.");
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const data = JSON.parse(reader.result as string) as ProfileExport;
          handleImportData(data);
        } catch {
          setImportError("Invalid profile file: could not parse JSON.");
        }
      };
      reader.readAsText(file);
    },
    [handleImportData],
  );

  function handleContextMenuSelect(key: string) {
    const profile = menuState.data;
    if (!profile) return;
    if (key === "load") void handleLoadWithPreview(profile.id);
    else if (key === "export") void handleExport(profile.id);
    else if (key === "rename") handleRename(profile);
    else if (key === "duplicate") handleDuplicate(profile);
    else if (key === "delete") setConfirmDelete(profile.id);
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="rounded-xl border border-border bg-surface-1 p-5 animate-pulse"
          >
            <div className="flex items-center justify-between">
              <div className="space-y-2">
                <div className="h-4 w-32 rounded bg-surface-3" />
                <div className="h-3 w-20 rounded bg-surface-3" />
              </div>
              <div className="flex gap-1">
                <div className="h-7 w-7 rounded-lg bg-surface-3" />
                <div className="h-7 w-7 rounded-lg bg-surface-3" />
                <div className="h-7 w-7 rounded-lg bg-surface-3" />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div
      className={`space-y-4 transition-all ${isDragOver ? "outline outline-2 outline-dashed outline-accent rounded-xl bg-accent/5" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-text-secondary">Saved Profiles</h3>
        <div className="flex gap-2">
          {profiles.length >= 2 && (
            <Button
              variant={compareMode ? "primary" : "secondary"}
              size="sm"
              title="Compare two profiles side by side to see differences"
              onClick={() => {
                setCompareMode(!compareMode);
                setSelectedForCompare([]);
              }}
            >
              <GitCompare size={14} /> Compare
            </Button>
          )}
          <Button
            variant="secondary"
            size="sm"
            title="Import a profile from a .json file"
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
          <Button size="sm" title="Save your current mod setup as a reusable profile" onClick={() => setShowCreate(true)}>
            <Plus size={14} /> Save Current
          </Button>
        </div>
      </div>

      {compareMode && (
        <div className="flex items-center gap-3 rounded-lg border border-accent/30 bg-accent/5 px-3 py-2">
          <p className="text-sm text-text-secondary">
            Select 2 profiles to compare ({selectedForCompare.length}/2 selected)
          </p>
          {selectedForCompare.length === 2 && (
            <Button
              size="sm"
              loading={compareProfiles.isPending}
              onClick={() => void handleCompare()}
            >
              Compare Selected
            </Button>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              setCompareMode(false);
              setSelectedForCompare([]);
            }}
          >
            Cancel
          </Button>
        </div>
      )}

      {showCreate && (
        <CreateProfileForm
          installedCount={installedCount}
          recognizedCount={recognizedCount}
          isPending={saveProfile.isPending}
          onSave={handleCreate}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {importError && (
        <p className="text-sm text-danger">{importError}</p>
      )}

      {profiles.length === 0 && !showCreate ? (
        <EmptyState
          icon={FolderOpen}
          title="No Saved Profiles"
          description="Profiles let you save and restore which mods are enabled or disabled. Install mods through the manager first, then save a snapshot of your setup here."
          actions={
            <>
              <Button size="sm" title="Save your current mod setup as a reusable profile" onClick={() => setShowCreate(true)}>
                <Plus size={14} /> Save Current
              </Button>
              <p className="text-xs text-text-muted mt-2">or drop a .json file here to import</p>
            </>
          }
        />
      ) : (
        <div className="space-y-2">
          {profiles.map((p) => (
            <Card key={p.id} onContextMenu={(e) => openMenu(e, p)}>
              {editingId === p.id ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Input
                      id={`edit-name-${p.id}`}
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleSaveRename()}
                      className="flex-1"
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={updateProfile.isPending}
                      onClick={handleSaveRename}
                    >
                      <Check size={14} className="text-success" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditingId(null)}
                    >
                      <X size={14} className="text-text-muted" />
                    </Button>
                  </div>
                  <textarea
                    className="w-full rounded-lg border border-border bg-surface-0 px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:border-accent focus:outline-none"
                    rows={2}
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    placeholder="Optional description..."
                  />
                </div>
              ) : duplicateId === p.id ? (
                <div className="flex items-center gap-2">
                  <Copy size={14} className="text-text-muted" />
                  <Input
                    id={`dup-name-${p.id}`}
                    value={duplicateName}
                    onChange={(e) => setDuplicateName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSaveDuplicate()}
                    className="flex-1"
                    placeholder="Name for the copy..."
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={duplicateProfile.isPending}
                    onClick={handleSaveDuplicate}
                  >
                    <Check size={14} className="text-success" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDuplicateId(null)}
                  >
                    <X size={14} className="text-text-muted" />
                  </Button>
                </div>
              ) : (
                <div className="flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      {compareMode && (
                        <input
                          type="checkbox"
                          checked={selectedForCompare.includes(p.id)}
                          onChange={() => handleCompareToggle(p.id)}
                          className="rounded border-border"
                        />
                      )}
                      <p
                        className="font-medium text-text-primary cursor-pointer"
                        onDoubleClick={() => handleRename(p)}
                      >
                        {p.name}
                      </p>
                      {p.is_active && !p.is_drifted && (
                        <span title="This profile is currently loaded and matches your mod state">
                          <Badge variant="success" prominent>Active</Badge>
                        </span>
                      )}
                      {p.is_active && p.is_drifted && (
                        <span title="This profile is loaded but your mod state has changed since loading it">
                          <Badge variant="warning" prominent>Active (modified)</Badge>
                        </span>
                      )}
                    </div>
                    {p.description && (
                      <p className="mt-0.5 truncate text-xs text-text-muted">
                        {p.description}
                      </p>
                    )}
                    <p className="text-xs text-text-muted">
                      {p.mod_count} mods &middot;{" "}
                      {new Date(p.created_at).toLocaleDateString()}
                      {p.last_loaded_at && (
                        <> &middot; loaded {timeAgo(isoToEpoch(p.last_loaded_at))}</>
                      )}
                    </p>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      title="Load this profile — preview changes before applying"
                      loading={
                        previewProfile.isPending &&
                        previewProfile.variables?.profileId === p.id
                      }
                      onClick={() => void handleLoadWithPreview(p.id)}
                    >
                      <FolderOpen size={14} className="text-accent" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      title="Export this profile as a .json file"
                      loading={
                        exportProfile.isPending &&
                        exportProfile.variables?.profileId === p.id
                      }
                      onClick={() => void handleExport(p.id)}
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
                        title="Delete this profile"
                        onClick={() => setConfirmDelete(p.id)}
                      >
                        <Trash2 size={14} className="text-danger" />
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      {menuState.visible && (
        <ContextMenu
          items={CONTEXT_MENU_ITEMS}
          position={menuState.position}
          onSelect={handleContextMenuSelect}
          onClose={closeMenu}
        />
      )}

      {diffPreview && (
        <ProfileDiffDialog
          diff={diffPreview}
          loading={loadProfile.isPending}
          onCancel={() => {
            setDiffPreview(null);
            setDiffProfileId(null);
          }}
          onConfirm={handleConfirmLoad}
        />
      )}

      {compareResult && (
        <ProfileCompareDialog
          compare={compareResult}
          onClose={() => {
            setCompareResult(null);
            setCompareMode(false);
            setSelectedForCompare([]);
          }}
        />
      )}
    </div>
  );
}
