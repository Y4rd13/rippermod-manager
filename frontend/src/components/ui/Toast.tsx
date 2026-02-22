import { AlertTriangle, CheckCircle, Info, X, XCircle } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { type Toast as ToastData, type ToastType, useToastStore } from "@/stores/toast-store";

const ICONS: Record<ToastType, typeof CheckCircle> = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

const ICON_COLORS: Record<ToastType, string> = {
  success: "text-success",
  error: "text-danger",
  warning: "text-warning",
  info: "text-accent",
};

const ACCENT_COLORS: Record<ToastType, string> = {
  success: "bg-success",
  error: "bg-danger",
  warning: "bg-warning",
  info: "bg-accent",
};

const AUTO_DISMISS_MS = 4000;

function ToastItem({ toast }: { toast: ToastData }) {
  const removeToast = useToastStore((s) => s.removeToast);
  const [visible, setVisible] = useState(false);
  const [dismissing, setDismissing] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const elRef = useRef<HTMLDivElement>(null);

  const startTimer = useCallback(() => {
    timerRef.current = setTimeout(() => {
      setDismissing(true);
    }, AUTO_DISMISS_MS);
  }, []);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = undefined;
    }
  }, []);

  useEffect(() => {
    requestAnimationFrame(() => setVisible(true));
    startTimer();
    return clearTimer;
  }, [startTimer, clearTimer]);

  useEffect(() => {
    if (!dismissing) return;
    const el = elRef.current;
    if (!el) {
      removeToast(toast.id);
      return;
    }
    const handleEnd = () => removeToast(toast.id);
    el.addEventListener("transitionend", handleEnd, { once: true });
    return () => el.removeEventListener("transitionend", handleEnd);
  }, [dismissing, toast.id, removeToast]);

  const handleMouseEnter = () => clearTimer();
  const handleMouseLeave = () => startTimer();
  const handleDismiss = () => {
    clearTimer();
    setDismissing(true);
  };

  const Icon = ICONS[toast.type];
  const show = visible && !dismissing;

  return (
    <div
      ref={elRef}
      role="alert"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      className={cn(
        "pointer-events-auto relative flex w-80 items-start gap-3 overflow-hidden",
        "rounded-lg border border-border bg-surface-1 shadow-lg px-4 py-3",
        "transition-all duration-300 ease-out",
        show ? "translate-x-0 opacity-100" : "translate-x-full opacity-0",
      )}
    >
      <div className={cn("absolute left-0 top-0 h-full w-0.5", ACCENT_COLORS[toast.type])} />
      <Icon size={18} className={cn("mt-0.5 shrink-0", ICON_COLORS[toast.type])} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-text-primary">{toast.title}</p>
        {toast.description && (
          <p className="mt-0.5 text-xs text-text-muted">{toast.description}</p>
        )}
      </div>
      <button
        onClick={handleDismiss}
        aria-label="Dismiss notification"
        className="shrink-0 rounded p-0.5 text-text-muted hover:text-text-secondary transition-colors"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col-reverse gap-2 pointer-events-none">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} />
      ))}
    </div>
  );
}
