import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  actions?: ReactNode;
}

export function EmptyState({ icon: Icon, title, description, actions }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16">
      <Icon size={48} className="text-text-muted/40 mb-4" />
      <h3 className="text-lg font-semibold text-text-primary mb-1">{title}</h3>
      <p className="text-sm text-text-muted max-w-sm text-center mb-4">{description}</p>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
