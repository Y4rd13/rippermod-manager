import { Power, PowerOff, Trash2 } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useToggleMod, useUninstallMod } from "@/hooks/mutations";
import { cn } from "@/lib/utils";
import type { InstalledModOut } from "@/types/api";

interface Props {
  mods: InstalledModOut[];
  gameName: string;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

type SortKey = "name" | "version" | "files" | "disabled";

export function InstalledModsTable({ mods, gameName }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [confirming, setConfirming] = useState<number | null>(null);
  const toggleMod = useToggleMod();
  const uninstallMod = useUninstallMod();

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sorted = [...mods].sort((a, b) => {
    const dir = sortDir === "asc" ? 1 : -1;
    switch (sortKey) {
      case "name":
        return a.name.localeCompare(b.name) * dir;
      case "version":
        return a.installed_version.localeCompare(b.installed_version) * dir;
      case "files":
        return (a.file_count - b.file_count) * dir;
      case "disabled":
        return (Number(a.disabled) - Number(b.disabled)) * dir;
      default:
        return 0;
    }
  });

  if (mods.length === 0) {
    return (
      <p className="py-4 text-sm text-text-muted">
        No installed mods. Install mods from the Archives tab.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-text-muted">
            {(
              [
                ["name", "Mod Name"],
                ["version", "Version"],
                ["files", "Files"],
                ["disabled", "Status"],
              ] as const
            ).map(([key, label]) => (
              <th
                key={key}
                className="cursor-pointer select-none pb-2 pr-4 hover:text-text-primary"
                onClick={() => handleSort(key)}
              >
                {label} {sortKey === key && (sortDir === "asc" ? "^" : "v")}
              </th>
            ))}
            <th className="pb-2 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((mod) => (
            <tr
              key={mod.id}
              className={cn(
                "border-b border-border/50",
                mod.disabled && "opacity-50",
              )}
            >
              <td className="py-2 pr-4">
                <span className="text-text-primary">{mod.name}</span>
                {mod.nexus_mod_id && (
                  <span className="ml-2 text-xs text-text-muted">
                    #{mod.nexus_mod_id}
                  </span>
                )}
              </td>
              <td className="py-2 pr-4 text-text-muted">
                {mod.installed_version || "--"}
              </td>
              <td className="py-2 pr-4 text-text-muted">{mod.file_count}</td>
              <td className="py-2 pr-4">
                <Badge variant={mod.disabled ? "danger" : "success"}>
                  {mod.disabled ? "Disabled" : "Enabled"}
                </Badge>
              </td>
              <td className="py-2 text-right">
                <div className="flex items-center justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={
                      toggleMod.isPending &&
                      toggleMod.variables?.modId === mod.id
                    }
                    onClick={() =>
                      toggleMod.mutate({ gameName, modId: mod.id })
                    }
                  >
                    {mod.disabled ? (
                      <Power size={14} className="text-success" />
                    ) : (
                      <PowerOff size={14} className="text-warning" />
                    )}
                  </Button>
                  {confirming === mod.id ? (
                    <Button
                      variant="danger"
                      size="sm"
                      loading={
                        uninstallMod.isPending &&
                        uninstallMod.variables?.modId === mod.id
                      }
                      onClick={() => {
                        uninstallMod.mutate({ gameName, modId: mod.id });
                        setConfirming(null);
                      }}
                    >
                      Confirm
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setConfirming(mod.id)}
                    >
                      <Trash2 size={14} className="text-danger" />
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

void formatBytes;
