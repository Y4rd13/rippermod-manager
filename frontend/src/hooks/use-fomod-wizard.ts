import { useCallback, useEffect, useMemo, useState } from "react";

import { useFomodConfig, useFomodInstall } from "@/hooks/mutations";
import {
  computeFlags,
  computeVisibleSteps,
  resolvePluginType,
} from "@/lib/fomod-evaluator";
import type {
  FomodConfigOut,
  FomodGroupOut,
  FomodPluginOut,
  FomodSelections,
  PluginTypeString,
} from "@/types/fomod";

function initializeDefaults(config: FomodConfigOut): FomodSelections {
  const selections: FomodSelections = {};

  for (let stepIdx = 0; stepIdx < config.steps.length; stepIdx++) {
    const step = config.steps[stepIdx];
    selections[stepIdx] = {};

    for (let groupIdx = 0; groupIdx < step.groups.length; groupIdx++) {
      const group = step.groups[groupIdx];
      const selected: number[] = [];

      if (group.type === "SelectAll") {
        group.plugins.forEach((_, i) => selected.push(i));
      } else {
        group.plugins.forEach((plugin, i) => {
          const dt = plugin.type_descriptor.default_type;
          if (dt === "Required" || dt === "Recommended") {
            selected.push(i);
          }
        });

        if (group.type === "SelectExactlyOne" && selected.length === 0) {
          const firstUsable = group.plugins.findIndex(
            (p) => p.type_descriptor.default_type !== "NotUsable",
          );
          if (firstUsable >= 0) {
            selected.push(firstUsable);
          }
        }
      }

      selections[stepIdx][groupIdx] = selected;
    }
  }

  return selections;
}

function validateGroup(group: FomodGroupOut, selected: number[]): boolean {
  switch (group.type) {
    case "SelectExactlyOne":
      return selected.length === 1;
    case "SelectAtLeastOne":
      return selected.length >= 1;
    default:
      return true;
  }
}

export function useFomodWizard(gameName: string, archiveFilename: string) {
  const [config, setConfig] = useState<FomodConfigOut | null>(null);
  const [visibleStepCursor, setVisibleStepCursor] = useState(0);
  const [selections, setSelections] = useState<FomodSelections>({});
  const [hasModified, setHasModified] = useState(false);

  const fetchConfig = useFomodConfig();
  const installMutation = useFomodInstall();

  // Load config on mount
  useEffect(() => {
    fetchConfig.mutate(
      { gameName, archiveFilename },
      {
        onSuccess: (data) => {
          setConfig(data);
          setSelections(initializeDefaults(data));
        },
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameName, archiveFilename]);

  // Derive flags from current selections
  const flags = useMemo(() => {
    if (!config) return {};
    return computeFlags(config, selections);
  }, [config, selections]);

  // Derive visible steps from flags
  const visibleSteps = useMemo(() => {
    if (!config) return [];
    return computeVisibleSteps(config, flags);
  }, [config, flags]);

  // Clamp inline so there's no stale-cursor render frame
  const clampedCursor = useMemo(() => {
    if (visibleSteps.length === 0) return 0;
    return Math.min(visibleStepCursor, visibleSteps.length - 1);
  }, [visibleSteps, visibleStepCursor]);

  const currentStep = visibleSteps[clampedCursor] ?? 0;

  // Sync state to the clamped value so next/back still work correctly
  useEffect(() => {
    if (clampedCursor !== visibleStepCursor) {
      setVisibleStepCursor(clampedCursor);
    }
  }, [clampedCursor, visibleStepCursor]);

  const getPluginType = useCallback(
    (plugin: FomodPluginOut): PluginTypeString => {
      return resolvePluginType(plugin.type_descriptor, flags);
    },
    [flags],
  );

  const selectPlugin = useCallback(
    (stepIdx: number, groupIdx: number, pluginIdx: number, groupType: string) => {
      setHasModified(true);
      setSelections((prev) => {
        const next = { ...prev };
        const stepSels = { ...(next[stepIdx] ?? {}) };
        const current = [...(stepSels[groupIdx] ?? [])];

        if (groupType === "SelectExactlyOne" || groupType === "SelectAtMostOne") {
          if (groupType === "SelectAtMostOne" && current.includes(pluginIdx)) {
            stepSels[groupIdx] = [];
          } else {
            stepSels[groupIdx] = [pluginIdx];
          }
        } else if (groupType === "SelectAtLeastOne" || groupType === "SelectAny") {
          const idx = current.indexOf(pluginIdx);
          if (idx >= 0) {
            current.splice(idx, 1);
          } else {
            current.push(pluginIdx);
          }
          stepSels[groupIdx] = current;
        }
        // SelectAll: no-op (all pre-selected)

        next[stepIdx] = stepSels;
        return next;
      });
    },
    [],
  );

  const canGoNext = useMemo(() => {
    if (!config) return false;
    const step = config.steps[currentStep];
    if (!step) return false;

    return step.groups.every((group, groupIdx) => {
      const selected = selections[currentStep]?.[groupIdx] ?? [];
      return validateGroup(group, selected);
    });
  }, [config, currentStep, selections]);

  const isFirstStep = clampedCursor === 0;
  const isLastStep =
    visibleSteps.length > 0 && clampedCursor >= visibleSteps.length - 1;
  const totalSteps = visibleSteps.length;

  const goNext = useCallback(() => {
    if (clampedCursor < visibleSteps.length - 1) {
      setVisibleStepCursor((c) => c + 1);
    }
  }, [visibleSteps.length, clampedCursor]);

  const goBack = useCallback(() => {
    if (clampedCursor > 0) {
      setVisibleStepCursor((c) => c - 1);
    }
  }, [clampedCursor]);

  const doInstall = useCallback(
    (modName: string) => {
      if (!config) return;
      installMutation.mutate({
        gameName,
        data: {
          archive_filename: archiveFilename,
          mod_name: modName,
          selections,
        },
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [config, gameName, archiveFilename, selections],
  );

  return {
    config,
    currentStep,
    visibleStepCursor: clampedCursor,
    visibleSteps,
    selections,
    flags,
    isLoading: fetchConfig.isPending,
    error: fetchConfig.error,
    isInstalling: installMutation.isPending,
    installSuccess: installMutation.isSuccess,
    installError: installMutation.error,
    canGoNext,
    isFirstStep,
    isLastStep,
    totalSteps,
    hasModified,
    selectPlugin,
    getPluginType,
    goNext,
    goBack,
    doInstall,
  };
}
