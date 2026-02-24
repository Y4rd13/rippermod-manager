import type {
  FomodCompositeDependency,
  FomodConfigOut,
  FomodStepOut,
  FomodTypeDescriptor,
  PluginTypeString,
} from "@/types/fomod";

export type FlagState = Record<string, string>;
type Selections = Record<number, Record<number, number[]>>;

/**
 * Recursively evaluate a composite dependency against flag state.
 * File conditions pass optimistically when installedFiles is absent.
 */
export function evaluateDependency(
  dep: FomodCompositeDependency,
  flags: FlagState,
  installedFiles?: Set<string>,
): boolean {
  const results: boolean[] = [];

  for (const fc of dep.flag_conditions) {
    results.push((flags[fc.name] ?? "") === fc.value);
  }

  for (const fileCond of dep.file_conditions) {
    if (!installedFiles) {
      // Optimistic: pass when no file info available
      results.push(true);
      continue;
    }
    const fileLower = fileCond.file.toLowerCase();
    const fileExists = installedFiles.has(fileLower);
    if (fileCond.state === "Active") {
      results.push(fileExists);
    } else {
      // Inactive or Missing
      results.push(!fileExists);
    }
  }

  for (const nested of dep.nested) {
    results.push(evaluateDependency(nested, flags, installedFiles));
  }

  if (results.length === 0) return true;

  return dep.operator === "And" ? results.every(Boolean) : results.some(Boolean);
}

/** Check if a step should be shown based on its visibility conditions. */
export function isStepVisible(
  step: FomodStepOut,
  flags: FlagState,
  installedFiles?: Set<string>,
): boolean {
  if (!step.visible) return true;
  return evaluateDependency(step.visible, flags, installedFiles);
}

/** Return array of original step indices that are currently visible. */
export function computeVisibleSteps(
  config: FomodConfigOut,
  flags: FlagState,
  installedFiles?: Set<string>,
): number[] {
  return config.steps
    .map((step, idx) => (isStepVisible(step, flags, installedFiles) ? idx : -1))
    .filter((idx) => idx >= 0);
}

/** Resolve the effective plugin type from a type descriptor given current flags. */
export function resolvePluginType(
  descriptor: FomodTypeDescriptor,
  flags: FlagState,
  installedFiles?: Set<string>,
): PluginTypeString {
  for (const pattern of descriptor.patterns) {
    if (evaluateDependency(pattern.dependency, flags, installedFiles)) {
      return pattern.type;
    }
  }
  return descriptor.default_type as PluginTypeString;
}

/**
 * Accumulate flags sequentially across visible steps, mirroring the backend's
 * compute_file_list() logic. Only processes steps visible given flags
 * accumulated so far.
 */
export function computeFlags(
  config: FomodConfigOut,
  selections: Selections,
  installedFiles?: Set<string>,
): FlagState {
  const flags: FlagState = {};

  for (let stepIdx = 0; stepIdx < config.steps.length; stepIdx++) {
    const step = config.steps[stepIdx];
    if (!isStepVisible(step, flags, installedFiles)) continue;

    const stepSels = selections[stepIdx] ?? {};
    for (let groupIdx = 0; groupIdx < step.groups.length; groupIdx++) {
      const group = step.groups[groupIdx];
      const selectedIndices = stepSels[groupIdx] ?? [];

      for (const pluginIdx of selectedIndices) {
        const plugin = group.plugins[pluginIdx];
        if (!plugin) continue;
        for (const flag of plugin.condition_flags) {
          flags[flag.name] = flag.value;
        }
      }
    }
  }

  return flags;
}
