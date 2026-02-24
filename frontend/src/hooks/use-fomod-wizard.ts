import { useCallback, useEffect, useMemo, useState } from "react";

import { useFomodConfig, useFomodInstall } from "@/hooks/mutations";
import type { FomodConfigOut, FomodGroupOut } from "@/types/fomod";

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
        // Pre-select Required and Recommended plugins
        group.plugins.forEach((plugin, i) => {
          const dt = plugin.type_descriptor.default_type;
          if (dt === "Required" || dt === "Recommended") {
            selected.push(i);
          }
        });

        // For SelectExactlyOne with no recommended, pre-select first non-NotUsable
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
  const [currentStep, setCurrentStep] = useState(0);
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

  const selectPlugin = useCallback(
    (stepIdx: number, groupIdx: number, pluginIdx: number, groupType: string) => {
      setHasModified(true);
      setSelections((prev) => {
        const next = { ...prev };
        const stepSels = { ...(next[stepIdx] ?? {}) };
        const current = [...(stepSels[groupIdx] ?? [])];

        if (groupType === "SelectExactlyOne" || groupType === "SelectAtMostOne") {
          // Radio behavior: check if clicking same option in AtMostOne to deselect
          if (groupType === "SelectAtMostOne" && current.includes(pluginIdx)) {
            stepSels[groupIdx] = [];
          } else {
            stepSels[groupIdx] = [pluginIdx];
          }
        } else if (groupType === "SelectAtLeastOne" || groupType === "SelectAny") {
          // Toggle behavior
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

  const isFirstStep = currentStep === 0;
  const isLastStep = config ? currentStep >= config.steps.length - 1 : true;
  const totalSteps = config?.total_steps ?? 0;

  const goNext = useCallback(() => {
    if (config && currentStep < config.steps.length - 1) {
      setCurrentStep((s) => s + 1);
    }
  }, [config, currentStep]);

  const goBack = useCallback(() => {
    if (currentStep > 0) {
      setCurrentStep((s) => s - 1);
    }
  }, [currentStep]);

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
    selections,
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
    goNext,
    goBack,
    doInstall,
  };
}
