import { AlertTriangle, type LucideIcon } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@/components/ui/Button";

interface Props {
  title: string;
  message: string;
  confirmLabel?: string;
  variant?: "danger" | "warning";
  icon?: LucideIcon;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
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
}: Props) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onCancel]);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="w-full max-w-sm rounded-xl border border-border bg-surface-1 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className={`mb-4 flex items-center gap-2 ${variant === "warning" ? "text-warning" : "text-danger"}`}
        >
          <Icon size={20} />
          <h3
            id="confirm-dialog-title"
            className="text-lg font-semibold text-text-primary"
          >
            {title}
          </h3>
        </div>
        <p className="mb-6 text-sm text-text-secondary">{message}</p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="danger" size="sm" loading={loading} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
