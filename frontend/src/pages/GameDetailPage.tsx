import { Link2, Package, RefreshCw, Scan } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router";

import { ModsTable } from "@/components/mods/ModsTable";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useCorrelate, useScanMods, useSyncNexus } from "@/hooks/mutations";
import { useGame, useMods, useUpdates } from "@/hooks/queries";
import { cn } from "@/lib/utils";

type Tab = "mods" | "updates";

export function GameDetailPage() {
  const { name = "" } = useParams();
  const { data: game } = useGame(name);
  const { data: mods = [] } = useMods(name);
  const { data: updates } = useUpdates(name);
  const scanMods = useScanMods();
  const syncNexus = useSyncNexus();
  const correlate = useCorrelate();
  const [tab, setTab] = useState<Tab>("mods");
  const [scanStatus, setScanStatus] = useState("");

  if (!game) {
    return <p className="text-text-muted">Loading game...</p>;
  }

  const handleFullScan = async () => {
    setScanStatus("Scanning local files...");
    const result = await scanMods.mutateAsync(name);
    setScanStatus(`Found ${result.files_found} files, ${result.groups_created} groups.`);

    setScanStatus("Syncing Nexus data...");
    try {
      await syncNexus.mutateAsync(name);
    } catch {
      // optional
    }

    setScanStatus("Correlating mods...");
    const corrResult = await correlate.mutateAsync(name);
    setScanStatus(
      `Done: ${corrResult.matched} matched, ${corrResult.unmatched} unmatched`,
    );
  };

  const isScanning = scanMods.isPending || syncNexus.isPending || correlate.isPending;

  const matched = mods.filter((m) => m.nexus_match).length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">{game.name}</h1>
          <p className="text-sm text-text-muted">{game.install_path}</p>
        </div>
        <Button onClick={handleFullScan} loading={isScanning}>
          <Scan size={16} /> Scan & Correlate
        </Button>
      </div>

      {scanStatus && (
        <p className="text-sm text-accent">{scanStatus}</p>
      )}

      <div className="grid grid-cols-3 gap-4">
        <Card>
          <div className="flex items-center gap-3">
            <Package size={18} className="text-success" />
            <div>
              <p className="text-xs text-text-muted">Local Mods</p>
              <p className="text-lg font-bold text-text-primary">{mods.length}</p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-3">
            <Link2 size={18} className="text-warning" />
            <div>
              <p className="text-xs text-text-muted">Nexus Matched</p>
              <p className="text-lg font-bold text-text-primary">{matched}</p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-3">
            <RefreshCw size={18} className="text-danger" />
            <div>
              <p className="text-xs text-text-muted">Updates Available</p>
              <p className="text-lg font-bold text-text-primary">
                {updates?.updates_available ?? "--"}
              </p>
            </div>
          </div>
        </Card>
      </div>

      <div className="flex gap-1 border-b border-border">
        {(["mods", "updates"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px",
              tab === t
                ? "border-accent text-accent"
                : "border-transparent text-text-muted hover:text-text-secondary",
            )}
          >
            {t === "mods" ? "Mods" : "Updates"}
          </button>
        ))}
      </div>

      {tab === "mods" && <ModsTable mods={mods} />}
      {tab === "updates" && (
        <div>
          {!updates?.updates.length ? (
            <p className="text-text-muted text-sm py-4">No updates detected. Run a scan first.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-text-muted">
                    <th className="pb-2 pr-4">Mod</th>
                    <th className="pb-2 pr-4">Local Version</th>
                    <th className="pb-2 pr-4">Nexus Version</th>
                    <th className="pb-2 pr-4">Author</th>
                    <th className="pb-2">Link</th>
                  </tr>
                </thead>
                <tbody>
                  {updates.updates.map((u) => (
                    <tr key={u.mod_group_id} className="border-b border-border/50">
                      <td className="py-2 pr-4 text-text-primary">{u.display_name}</td>
                      <td className="py-2 pr-4 text-text-muted">{u.local_version}</td>
                      <td className="py-2 pr-4 text-success font-medium">{u.nexus_version}</td>
                      <td className="py-2 pr-4 text-text-muted">{u.author}</td>
                      <td className="py-2">
                        <a
                          href={u.nexus_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-accent hover:underline"
                        >
                          Nexus
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
