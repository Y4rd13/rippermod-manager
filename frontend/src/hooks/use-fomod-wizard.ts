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
  PluginTypeString,
} from "@/types/fomod";

type Selections = Record<number, Record<number, number[]>>;

function initializeDefaults(config: FomodConfigOut): Selections {
  const selections: Selections = {};

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
  const [selections, setSelections] = useState<Selections>({});
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

  // The original config step index for the current cursor position
  const currentStep = visibleSteps[visibleStepCursor] ?? 0;

  // Clamp cursor if it goes out of range (e.g. step hidden while user is on it)
  useEffect(() => {
    if (visibleSteps.length > 0 && visibleStepCursor >= visibleSteps.length) {
      setVisibleStepCursor(visibleSteps.length - 1);
    }
  }, [visibleSteps, visibleStepCursor]);

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

  const isFirstStep = visibleStepCursor === 0;
  const isLastStep =
    visibleSteps.length === 0 || visibleStepCursor >= visibleSteps.length - 1;
  const totalSteps = visibleSteps.length;

  const goNext = useCallback(() => {
    if (visibleStepCursor < visibleSteps.length - 1) {
      setVisibleStepCursor((c) => c + 1);
    }
  }, [visibleSteps.length, visibleStepCursor]);

  const goBack = useCallback(() => {
    if (visibleStepCursor > 0) {
      setVisibleStepCursor((c) => c - 1);
    }
  }, [visibleStepCursor]);

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
    visibleStepCursor,
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
