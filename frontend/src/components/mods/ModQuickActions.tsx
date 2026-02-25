import { Eye, EyeOff, Heart, Loader2 } from "lucide-react";

import { useAbstainMod, useEndorseMod, useTrackMod, useUntrackMod } from "@/hooks/mutations";

interface Props {
  isEndorsed: boolean;
  isTracked: boolean;
  modId: number;
  gameName: string;
}

export function ModQuickActions({ isEndorsed, isTracked, modId, gameName }: Props) {
  const endorse = useEndorseMod();
  const abstain = useAbstainMod();
  const track = useTrackMod();
  const untrack = useUntrackMod();

  const endorsePending = endorse.isPending || abstain.isPending;
  const trackPending = track.isPending || untrack.isPending;

  return (
    <div className="flex items-center gap-0.5">
      <button
        type="button"
        title={isEndorsed ? "Remove Endorsement" : "Endorse"}
        disabled={endorsePending}
        className={`rounded p-1 transition-colors ${
          isEndorsed
            ? "text-danger hover:text-danger/70"
            : "text-text-muted hover:text-danger"
        } disabled:opacity-50`}
        onClick={(e) => {
          e.stopPropagation();
          if (isEndorsed) abstain.mutate({ gameName, modId });
          else endorse.mutate({ gameName, modId });
        }}
      >
        {endorsePending ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <Heart size={14} fill={isEndorsed ? "currentColor" : "none"} />
        )}
      </button>

      <button
        type="button"
        title={isTracked ? "Untrack" : "Track"}
        disabled={trackPending}
        className={`rounded p-1 transition-colors ${
          isTracked
            ? "text-accent hover:text-accent/70"
            : "text-text-muted hover:text-accent"
        } disabled:opacity-50`}
        onClick={(e) => {
          e.stopPropagation();
          if (isTracked) untrack.mutate({ gameName, modId });
          else track.mutate({ gameName, modId });
        }}
      >
        {trackPending ? (
          <Loader2 size={14} className="animate-spin" />
        ) : isTracked ? (
          <EyeOff size={14} />
        ) : (
          <Eye size={14} />
        )}
      </button>
    </div>
  );
}
