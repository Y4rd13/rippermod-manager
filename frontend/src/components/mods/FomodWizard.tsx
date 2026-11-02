import { AlertTriangle, Check, ChevronLeft, ChevronRight, Loader2, Package } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { useFomodWizard } from "@/hooks/use-fomod-wizard";
import { cn } from "@/lib/utils";
import type { FomodConfigOut, FomodGroupOut, FomodPluginOut, PluginTypeString } from "@/types/fomod";

interface Props {
  gameName: string;
  archiveFilename: string;
  onDismiss: () => void;
  onInstallComplete: () => void;
}

function StepIndicator({
  cursor,
  totalVisible,
  visibleSteps,
  config,
}: {
  cursor: number;
  totalVisible: number;
  visibleSteps: number[];
  config: FomodConfigOut;
}) {
  if (totalVisible <= 1) return null;
  return (
    <div className="flex items-center gap-2">
      {visibleSteps.map((origIdx, i) => (
        <div key={origIdx} className="flex items-center gap-2">
          <div
            title={config.steps[origIdx]?.name}
            className={cn(
              "flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold transition-colors",
              i < cursor
                ? "bg-success text-white"
                : i === cursor
                  ? "bg-accent text-white"
                  : "bg-surface-3 text-text-muted",
            )}
          >
            {i < cursor ? <Check size={12} /> : i + 1}
          </div>
          {i < totalVisible - 1 && (
            <div
              className={cn("h-px w-6", i < cursor ? "bg-success" : "bg-border")}
            />
          )}
        </div>
      ))}
    </div>
  );
}

function TypeBadge({ type }: { type: string }) {
  switch (type) {
    case "Required":
      return (
        <span className="text-[10px] font-medium bg-accent/20 text-accent-text px-1.5 py-0.5 rounded">
          Required
        </span>
      );
    case "Recommended":
      return (
        <span className="text-[10px] font-medium bg-success/20 text-success px-1.5 py-0.5 rounded">
          Recommended
        </span>
      );
    case "NotUsable":
      return (
        <span className="text-[10px] font-medium bg-danger/20 text-danger px-1.5 py-0.5 rounded">
          Not usable
        </span>
      );
    case "CouldBeUsable":
      return (
        <span className="text-[10px] font-medium bg-warning/20 text-warning px-1.5 py-0.5 rounded flex items-center gap-0.5">
          <AlertTriangle size={10} /> Experimental
        </span>
      );
    default:
      return null;
  }
}

function PluginOption({
  plugin,
  pluginType,
  selected,
  disabled,
  inputType,
  inputName,
  onChange,
}: {
  plugin: FomodPluginOut;
  pluginType: PluginTypeString;
  selected: boolean;
  disabled: boolean;
  inputType: "radio" | "checkbox";
  inputName: string;
  onChange: () => void;
}) {
  const isNotUsable = pluginType === "NotUsable";
  const isRequired = pluginType === "Required";
  const isDisabled = disabled || isNotUsable || isRequired;

  return (
    <label
      className={cn(
        "flex items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors cursor-pointer",
        selected
          ? "border-accent/50 bg-accent/5"
          : "border-border hover:border-border-bright",
        isDisabled && "opacity-60 cursor-not-allowed",
      )}
    >
      <input
        type={inputType}
        name={inputName}
        checked={selected}
        disabled={isDisabled}
        onChange={onChange}
        className="mt-0.5 shrink-0"
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={cn("text-sm font-medium", isNotUsable ? "text-text-muted" : "text-text-primary")}>
            {plugin.name}
          </span>
          <TypeBadge type={pluginType} />
        </div>
        {plugin.description && (
          <p className="text-xs text-text-muted mt-0.5 line-clamp-2">{plugin.description}</p>
        )}
      </div>
    </label>
  );
}

function GroupSection({
  group,
  groupIdx,
  stepIdx,
  selected,
  onSelect,
  getPluginType,
}: {
  group: FomodGroupOut;
  groupIdx: number;
  stepIdx: number;
  selected: number[];
  onSelect: (stepIdx: number, groupIdx: number, pluginIdx: number, groupType: string) => void;
  getPluginType: (plugin: FomodPluginOut) => PluginTypeString;
}) {
  const isRadio = group.type === "SelectExactlyOne" || group.type === "SelectAtMostOne";
  const isSelectAll = group.type === "SelectAll";
  const inputType = isRadio ? "radio" : "checkbox";
  const inputName = `step-${stepIdx}-group-${groupIdx}`;

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <h4 className="text-sm font-semibold text-text-primary">{group.name}</h4>
        <span className="text-[10px] text-text-muted">
          {group.type === "SelectExactlyOne" && "Pick one"}
          {group.type === "SelectAtMostOne" && "Pick one or none"}
          {group.type === "SelectAtLeastOne" && "Pick at least one"}
          {group.type === "SelectAny" && "Pick any"}
          {group.type === "SelectAll" && "All required"}
        </span>
      </div>
      <div className="space-y-1.5">
        {group.plugins.map((plugin, pluginIdx) => (
          <PluginOption
            key={pluginIdx}
            plugin={plugin}
            pluginType={getPluginType(plugin)}
            selected={selected.includes(pluginIdx)}
            disabled={isSelectAll}
            inputType={inputType}
            inputName={inputName}
            onChange={() => onSelect(stepIdx, groupIdx, pluginIdx, group.type)}
          />
        ))}
      </div>
    </div>
  );
}

export function FomodWizard({ gameName, archiveFilename, onDismiss, onInstallComplete }: Props) {
  const wizard = useFomodWizard(gameName, archiveFilename);
  const derivedName = useMemo(
    () => wizard.config?.module_name || archiveFilename.replace(/\.[^.]+$/, ""),
    [wizard.config, archiveFilename],
  );
  const [modNameOverride, setModNameOverride] = useState<string | null>(null);
  const modName = modNameOverride ?? derivedName;

  // Close on install success
  useEffect(() => {
    if (wizard.installSuccess) {
      onInstallComplete();
    }
  }, [wizard.installSuccess, onInstallComplete]);

  const requestDismiss = useCallback(() => {
    if (wizard.hasModified) {
      if (window.confirm("Discard FOMOD selections?")) {
        onDismiss();
      }
    } else {
      onDismiss();
    }
  }, [onDismiss, wizard.hasModified]);

  const currentStepData = wizard.config?.steps[wizard.currentStep];
  const stepName = wizard.isReview
    ? "Review"
    : currentStepData?.name || `Step ${wizard.visibleStepCursor + 1}`;

  const filesCount = useMemo(() => {
    if (!wizard.config) return 0;
    let count = wizard.config.required_install_files.length;
    const stepSels = wizard.selections[wizard.currentStep] ?? {};
    for (const [_gIdx, pIndices] of Object.entries(stepSels)) {
      const group = currentStepData?.groups[Number(_gIdx)];
      if (group) {
        for (const pIdx of pIndices) {
          const plugin = group.plugins[pIdx];
          if (plugin) count += plugin.files.length;
        }
      }
    }
    return count;
  }, [wizard.config, wizard.selections, wizard.currentStep, currentStepData]);

  return (
    <Dialog
      onClose={requestDismiss}
      titleId="fomod-wizard-title"
      closeOnEscape={!wizard.isInstalling}
      backdropClassName="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      className="w-full max-w-2xl max-h-[85vh] flex flex-col rounded-xl border border-border bg-surface-1"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-3">
          <Package size={20} className="text-accent-text" />
          <div>
            <h3 id="fomod-wizard-title" className="text-base font-semibold text-text-primary">
              {wizard.config?.module_name || "FOMOD Installer"}
            </h3>
            {(wizard.totalSteps > 1 || wizard.isReview) && (
              <p className="text-xs text-text-muted">{stepName}</p>
            )}
          </div>
        </div>
        {wizard.config && wizard.totalSteps > 1 && (
          <StepIndicator
            cursor={wizard.visibleStepCursor}
            totalVisible={wizard.totalSteps}
            visibleSteps={wizard.visibleSteps}
            config={wizard.config}
          />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {wizard.isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={24} className="animate-spin text-accent-text" />
            <span className="ml-2 text-sm text-text-muted">Loading installer config...</span>
          </div>
        )}

        {wizard.error && (
          <div className="rounded-lg border border-danger/30 bg-danger/5 p-4">
            <p className="text-sm text-danger">Failed to load FOMOD config</p>
            <p className="text-xs text-text-muted mt-1">{wizard.error.message}</p>
          </div>
        )}

        {currentStepData && !wizard.isReview && (
          <div className="space-y-5">
            {currentStepData.groups.map((group, groupIdx) => (
              <GroupSection
                key={groupIdx}
                group={group}
                groupIdx={groupIdx}
                stepIdx={wizard.currentStep}
                selected={wizard.selections[wizard.currentStep]?.[groupIdx] ?? []}
                onSelect={wizard.selectPlugin}
                getPluginType={wizard.getPluginType}
              />
            ))}
          </div>
        )}

        {wizard.config && wizard.isReview && (
          <div className="space-y-3">
            <h4 className="text-sm font-semibold text-text-primary">Review</h4>
            {wizard.isPreviewing && (
              <div className="flex items-center gap-2 text-sm text-text-muted">
                <Loader2 size={14} className="animate-spin" /> Listing the files to install...
              </div>
            )}
            {wizard.previewError && (
              <p className="rounded-lg border border-warning/30 bg-warning/5 p-3 text-sm text-warning">
                Could not preview the files: {wizard.previewError.message}
              </p>
            )}
            {wizard.preview && !wizard.isPreviewing && !wizard.previewError && (
              <>
                <p className="text-sm text-text-secondary">
                  {wizard.preview.total_files} file(s) will be installed
                </p>
                <ul className="max-h-64 overflow-y-auto rounded-lg border border-border bg-surface-2 p-2 font-mono text-xs text-text-secondary">
                  {wizard.preview.files.map((f, i) => (
                    // Two sources can target one path: the index keeps keys unique.
                    <li key={`${i}:${f.game_relative_path}`} className="truncate" title={f.game_relative_path}>
                      {f.game_relative_path}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}

        {/* Mod name input on the Review step */}
        {wizard.config && wizard.isReview && (
          <div className="mt-5 pt-4 border-t border-border">
            <label className="block text-xs font-medium text-text-secondary mb-1">
              Mod name
            </label>
            <input
              type="text"
              value={modName}
              onChange={(e) => setModNameOverride(e.target.value)}
              className="w-full rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
            />
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-border px-6 py-3">
        <span className="text-xs text-text-muted">
          {wizard.config &&
            !wizard.isReview &&
            `${filesCount} file mapping${filesCount !== 1 ? "s" : ""}`}
        </span>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => {
            if (wizard.hasModified) {
              if (window.confirm("Discard FOMOD selections?")) onDismiss();
            } else {
              onDismiss();
            }
          }}>
            Cancel
          </Button>
          {((wizard.isReview && wizard.totalSteps > 0) ||
            (!wizard.isReview && !wizard.isFirstStep)) && (
            <Button variant="secondary" size="sm" onClick={wizard.goBack}>
              <ChevronLeft size={14} /> Back
            </Button>
          )}
          {wizard.config && !wizard.isReview && (
            <Button
              size="sm"
              onClick={wizard.isLastStep ? wizard.goToReview : wizard.goNext}
              disabled={!wizard.canGoNext}
            >
              Next <ChevronRight size={14} />
            </Button>
          )}
          {wizard.isReview && wizard.config && (
            <Button
              size="sm"
              onClick={() => wizard.doInstall(modName)}
              disabled={!modName.trim()}
              loading={wizard.isInstalling}
            >
              Install
            </Button>
          )}
        </div>
      </div>
    </Dialog>
  );
}
