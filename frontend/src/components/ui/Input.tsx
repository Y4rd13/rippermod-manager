import { type InputHTMLAttributes, forwardRef } from "react";

import { cn } from "@/lib/utils";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, id, ...props }, ref) => (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={id} className="text-sm font-medium text-text-secondary">
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={id}
        className={cn(
          "rounded-lg border bg-surface-1 px-3 py-2 text-sm text-text-primary",
          "placeholder:text-text-muted",
          "focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent",
          "transition-colors",
          error ? "border-danger" : "border-border",
          className,
        )}
        {...props}
      />
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  ),
);

Input.displayName = "Input";
