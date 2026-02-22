import { cn } from "@/lib/utils";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  onClick?: () => void;
  onContextMenu?: (e: React.MouseEvent) => void;
}

export function Card({ children, className, title, onClick, onContextMenu }: CardProps) {
  return (
    <div
      className={cn("rounded-xl border border-border bg-surface-1 p-5", onClick && "cursor-pointer", className)}
      title={title}
      onClick={onClick}
      onContextMenu={onContextMenu}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className }: CardProps) {
  return <div className={cn("mb-4", className)}>{children}</div>;
}

export function CardTitle({ children, className }: CardProps) {
  return <h3 className={cn("text-lg font-semibold text-text-primary", className)}>{children}</h3>;
}
