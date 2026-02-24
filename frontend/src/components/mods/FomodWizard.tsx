import { AlertTriangle, Check, ChevronLeft, ChevronRight, Loader2, Package } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { useFomodWizard } from "@/hooks/use-fomod-wizard";
import { cn } from "@/lib/utils";
import type { FomodGroupOut, FomodPluginOut } from "@/types/fomod";

interface Props {
  gameName: string;
  archiveFilename: string;
  onDismiss: () => void;
  onInstallComplete: () => void;
}

function StepIndicator({ current, total }: { current: number; total: number }) {
  if (total <= 1) return null;
  return (
    <div className="flex items-center gap-2">
      {Array.from({ length: total }, (_, i) => (
        <div key={i} className="flex items-center gap-2">
          <div
            className={cn(
              "flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold transition-colors",
              i < current
                ? "bg-success text-white"
                : i === current
                  ? "bg-accent text-white"
                  : "bg-surface-3 text-text-muted",
            )}
          >
            {i < current ? <Check size={12} /> : i + 1}
          </div>
          {i < total - 1 && (
            <div
              className={cn("h-px w-6", i < current ? "bg-success" : "bg-border")}
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
        <span className="text-[10px] font-medium bg-accent/20 text-accent px-1.5 py-0.5 rounded">
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
  selected,
  disabled,
  inputType,
  inputName,
  onChange,
}: {
  plugin: FomodPluginOut;
  selected: boolean;
  disabled: boolean;
  inputType: "radio" | "checkbox";
  inputName: string;
  onChange: () => void;
}) {
  const pluginType = plugin.type_descriptor.default_type;
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
}: {
  group: FomodGroupOut;
  groupIdx: number;
  stepIdx: number;
  selected: number[];
  onSelect: (stepIdx: number, groupIdx: number, pluginIdx: number, groupType: string) => void;
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

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (wizard.hasModified) {
          if (window.confirm("Discard FOMOD selections?")) {
            onDismiss();
          }
        } else {
          onDismiss();
        }
      }
    },
    [onDismiss, wizard.hasModified],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  const currentStepData = wizard.config?.steps[wizard.currentStep];
  const stepName = currentStepData?.name || `Step ${wizard.currentStep + 1}`;

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
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          if (wizard.hasModified) {
            if (window.confirm("Discard FOMOD selections?")) onDismiss();
          } else {
            onDismiss();
          }
        }
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="fomod-wizard-title"
        className="w-full max-w-2xl max-h-[85vh] flex flex-col rounded-xl border border-border bg-surface-1"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-3">
            <Package size={20} className="text-accent" />
            <div>
              <h3 id="fomod-wizard-title" className="text-base font-semibold text-text-primary">
                {wizard.config?.module_name || "FOMOD Installer"}
              </h3>
              {wizard.totalSteps > 1 && (
                <p className="text-xs text-text-muted">{stepName}</p>
              )}
            </div>
          </div>
          {wizard.totalSteps > 1 && (
            <StepIndicator current={wizard.currentStep} total={wizard.totalSteps} />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {wizard.isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={24} className="animate-spin text-accent" />
              <span className="ml-2 text-sm text-text-muted">Loading installer config...</span>
            </div>
          )}

          {wizard.error && (
            <div className="rounded-lg border border-danger/30 bg-danger/5 p-4">
              <p className="text-sm text-danger">Failed to load FOMOD config</p>
              <p className="text-xs text-text-muted mt-1">{wizard.error.message}</p>
            </div>
          )}

          {currentStepData && (
            <div className="space-y-5">
              {currentStepData.groups.map((group, groupIdx) => (
                <GroupSection
                  key={groupIdx}
                  group={group}
                  groupIdx={groupIdx}
                  stepIdx={wizard.currentStep}
                  selected={wizard.selections[wizard.currentStep]?.[groupIdx] ?? []}
                  onSelect={wizard.selectPlugin}
                />
              ))}
            </div>
          )}

          {/* Mod name input on last step */}
          {wizard.config && wizard.isLastStep && (
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
            {wizard.config && `${filesCount} file mapping${filesCount !== 1 ? "s" : ""}`}
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
            {!wizard.isFirstStep && (
              <Button variant="secondary" size="sm" onClick={wizard.goBack}>
                <ChevronLeft size={14} /> Back
              </Button>
            )}
            {!wizard.isLastStep && (
              <Button size="sm" onClick={wizard.goNext} disabled={!wizard.canGoNext}>
                Next <ChevronRight size={14} />
              </Button>
            )}
            {wizard.isLastStep && wizard.config && (
              <Button
                size="sm"
                onClick={() => wizard.doInstall(modName)}
                disabled={!wizard.canGoNext || !modName.trim()}
                loading={wizard.isInstalling}
              >
                Install
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
