import { create } from "zustand";

export type ToastType = "success" | "error" | "warning" | "info";

const TOAST_DURATIONS: Record<ToastType, number> = {
  error: 8000,
  warning: 6000,
  success: 4000,
  info: 4000,
};

export interface Toast {
  id: string;
  type: ToastType;
  title: string;
  description?: string;
  duration: number;
}

interface ToastState {
  toasts: Toast[];
  addToast: (toast: Omit<Toast, "id" | "duration">) => void;
  removeToast: (id: string) => void;
}

const MAX_TOASTS = 3;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  addToast: (toast) =>
    set((state) => {
      const newToast: Toast = {
        ...toast,
        id: crypto.randomUUID(),
        duration: TOAST_DURATIONS[toast.type],
      };
      const toasts = [...state.toasts, newToast];
      return { toasts: toasts.length > MAX_TOASTS ? toasts.slice(-MAX_TOASTS) : toasts };
    }),
  removeToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));

export const toast = {
  success: (title: string, description?: string) =>
    useToastStore.getState().addToast({ type: "success", title, description }),
  error: (title: string, description?: string) =>
    useToastStore.getState().addToast({ type: "error", title, description }),
  warning: (title: string, description?: string) =>
    useToastStore.getState().addToast({ type: "warning", title, description }),
  info: (title: string, description?: string) =>
    useToastStore.getState().addToast({ type: "info", title, description }),
};
