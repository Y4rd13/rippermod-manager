import { cn } from "@/lib/utils";

type Variant = "success" | "warning" | "danger" | "neutral";

const variantStyles: Record<Variant, string> = {
  success: "bg-success/10 text-success border-success/20",
  warning: "bg-warning/10 text-warning border-warning/20",
  danger: "bg-danger/10 text-danger border-danger/20",
  neutral: "bg-surface-3 text-text-secondary border-border",
};

interface BadgeProps {
  variant?: Variant;
  children: React.ReactNode;
  className?: string;
}

export function Badge({ variant = "neutral", children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
        variantStyles[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function ConfidenceBadge({ score }: { score: number }) {
  const variant = score >= 0.9 ? "success" : score >= 0.75 ? "warning" : "danger";
  const pct = Math.round(score * 100);
  return <Badge variant={variant}>{pct}%</Badge>;
}
