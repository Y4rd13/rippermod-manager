import { AlertTriangle, type LucideIcon } from "lucide-react";
import { type ReactNode, useId } from "react";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";

interface Props {
  title: string;
  message: string;
  confirmLabel?: string;
  variant?: "danger" | "warning";
  icon?: LucideIcon;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  /** Optional extra content rendered between the message and the action buttons. */
  children?: ReactNode;
  /** Optional non-destructive alternative shown between Cancel and the confirm button. */
  secondaryLabel?: string;
  onSecondary?: () => void;
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Confirm",
  variant = "danger",
  icon: Icon = AlertTriangle,
  loading = false,
  onConfirm,
  onCancel,
  children,
  secondaryLabel,
  onSecondary,
}: Props) {
  const dialogId = useId();

  return (
    <Dialog
      onClose={onCancel}
      titleId={`confirm-dialog-title-${dialogId}`}
      closeOnEscape={!loading}
      closeOnBackdrop={!loading}
      backdropClassName="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      className="w-full max-w-sm rounded-xl border border-border bg-surface-1 p-6"
    >
      <div
        className={`mb-4 flex items-center gap-2 ${variant === "warning" ? "text-warning" : "text-danger"}`}
      >
        <Icon size={20} />
        <h3
          id={`confirm-dialog-title-${dialogId}`}
          className="text-lg font-semibold text-text-primary"
        >
          {title}
        </h3>
      </div>
      <p className={`text-sm text-text-secondary ${children ? "mb-3" : "mb-6"}`}>{message}</p>
      {children && <div className="mb-6">{children}</div>}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" size="sm" disabled={loading} onClick={onCancel}>
          Cancel
        </Button>
        {secondaryLabel && onSecondary && (
          <Button variant="secondary" size="sm" disabled={loading} onClick={onSecondary}>
            {secondaryLabel}
          </Button>
        )}
        {/* Always danger-styled: both warning and danger dialogs guard destructive/state-changing actions */}
        <Button variant="danger" size="sm" loading={loading} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </div>
    </Dialog>
  );
}
