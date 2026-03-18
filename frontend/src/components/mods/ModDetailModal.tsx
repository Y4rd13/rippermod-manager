import {
  ArrowUp,
  ExternalLink,
  Eye,
  EyeOff,
  Gamepad2,
  Heart,
  Puzzle,
  X,
} from "lucide-react";
import { useCallback, useEffect } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useAbstainMod, useEndorseMod, useTrackMod, useUntrackMod } from "@/hooks/mutations";
import { useModSummary } from "@/hooks/queries";
import type { ModUpdate } from "@/types/api";
import type { ReactNode } from "react";

interface Props {
  gameDomain: string;
  gameName?: string;
  modId: number;
  update?: ModUpdate;
  action?: ReactNode;
  onClose: () => void;
}

export function ModDetailModal({ gameDomain, gameName, modId, update, action, onClose }: Props) {
  const { data: detail, isLoading } = useModSummary(modId);
  const endorseMod = useEndorseMod();
  const abstainMod = useAbstainMod();
  const trackMod = useTrackMod();
  const untrackMod = useUntrackMod();

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [handleKeyDown]);

  const nexusUrl = detail?.nexus_url
    ?? `https://www.nexusmods.com/${gameDomain}/mods/${modId}`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-lg max-h-[80vh] rounded-xl border border-border bg-surface-0 overflow-hidden flex flex-col animate-modal-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Loading skeleton */}
        {isLoading && (
          <div className="animate-pulse p-5 space-y-3">
            <div className="h-5 w-3/4 bg-surface-2 rounded" />
            <div className="h-3 w-1/2 bg-surface-2 rounded" />
            <div className="h-8 w-full bg-surface-2 rounded mt-4" />
          </div>
        )}

        {detail && (
          <>
            {/* Header */}
            <div className="flex-shrink-0 px-5 pt-5 pb-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <h2 className="text-lg font-bold text-text-primary leading-tight truncate" title={detail.name}>
                    {detail.name}
                  </h2>
                  <div className="flex items-center gap-3 mt-1.5 text-xs text-text-muted flex-wrap">
                    {detail.author && (
                      <span className="text-text-secondary">by {detail.author}</span>
                    )}
                    {detail.version && <span>v{detail.version}</span>}
                    {update && (
                      <Badge variant="warning"><ArrowUp size={10} className="mr-0.5" />v{update.nexus_version} available</Badge>
                    )}
                    {detail.category && !/^\d+$/.test(detail.category) && (
                      <Badge variant="neutral">{detail.category}</Badge>
                    )}
                  </div>
                </div>
                <button
                  className="rounded-lg p-1.5 text-text-muted hover:text-text-primary hover:bg-surface-2 transition-colors flex-shrink-0"
                  onClick={onClose}
                >
                  <X size={18} />
                </button>
              </div>

              {/* Prominent CTA */}
              <Button
                variant="primary"
                size="md"
                className="w-full mt-4"
                onClick={() => openUrl(nexusUrl).catch(() => {})}
              >
                <ExternalLink size={16} />
                View on Nexus Mods
              </Button>
            </div>

            {/* Scrollable content — requirements only */}
            <div className="flex-1 overflow-y-auto px-5 pb-3 space-y-3">
              {detail.dlc_requirements && detail.dlc_requirements.length > 0 && (
                <div className="rounded-lg border border-warning/30 bg-warning/5 p-3">
                  <div className="flex items-center gap-1.5 text-xs text-warning mb-2">
                    <Gamepad2 size={12} />
                    <span className="font-medium uppercase tracking-wide">Requires DLC</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {detail.dlc_requirements.map((dlc) => (
                      <span
                        key={dlc.expansion_id ?? dlc.expansion_name}
                        className="inline-flex items-center gap-1.5 rounded-md border border-warning/20 bg-warning/10 px-2.5 py-1 text-xs font-medium text-warning"
                      >
                        {dlc.expansion_name}
                        {dlc.notes && <span className="text-warning/70 font-normal">{dlc.notes}</span>}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {detail.requirements && detail.requirements.length > 0 && (
                <div className="rounded-lg border border-border bg-surface-1 p-3">
                  <div className="flex items-center gap-1.5 text-xs text-text-muted mb-2">
                    <Puzzle size={12} />
                    <span className="font-medium uppercase tracking-wide">Requires</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {detail.requirements.map((req) => {
                      const href = req.url
                        || (req.required_mod_id
                          ? `https://www.nexusmods.com/${gameDomain}/mods/${req.required_mod_id}`
                          : "");
                      return (
                        <button
                          key={`${req.nexus_mod_id}-${req.required_mod_id ?? req.mod_name}`}
                          className="inline-flex items-center gap-1.5 rounded-md border border-accent/20 bg-accent/5 px-2.5 py-1 text-xs font-medium text-accent hover:bg-accent/15 hover:border-accent/40 transition-colors disabled:opacity-50 disabled:cursor-default"
                          onClick={() => { if (href) openUrl(href).catch(() => {}); }}
                          disabled={!href}
                        >
                          {req.mod_name || "Unknown mod"}
                          {req.notes && <span className="text-text-muted font-normal">{req.notes}</span>}
                          {req.is_external && <ExternalLink size={10} />}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Footer — actions */}
            <div className="flex-shrink-0 border-t border-border px-5 py-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                {gameName && (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={endorseMod.isPending || abstainMod.isPending}
                      onClick={() => {
                        if (detail.is_endorsed) abstainMod.mutate({ gameName, modId });
                        else endorseMod.mutate({ gameName, modId });
                      }}
                      className={detail.is_endorsed ? "text-danger" : ""}
                    >
                      <Heart size={14} fill={detail.is_endorsed ? "currentColor" : "none"} />
                      {detail.is_endorsed ? "Endorsed" : "Endorse"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={trackMod.isPending || untrackMod.isPending}
                      onClick={() => {
                        if (detail.is_tracked) untrackMod.mutate({ gameName, modId });
                        else trackMod.mutate({ gameName, modId });
                      }}
                      className={detail.is_tracked ? "text-accent" : ""}
                    >
                      {detail.is_tracked ? <EyeOff size={14} /> : <Eye size={14} />}
                      {detail.is_tracked ? "Tracked" : "Track"}
                    </Button>
                  </>
                )}
              </div>
              {action && <div className="flex items-center gap-2">{action}</div>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
