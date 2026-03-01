import { AlertTriangle, Check, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";

type Variant = "success" | "warning" | "danger" | "neutral";

const variantStyles: Record<Variant, string> = {
  success: "bg-success/10 text-success border-success/20",
  warning: "bg-warning/10 text-warning border-warning/20",
  danger: "bg-danger/10 text-danger border-danger/20",
  neutral: "bg-surface-3 text-text-secondary border-border",
};

const prominentVariantStyles: Record<Variant, string> = {
  success: "bg-success/90 text-white border-success shadow-sm shadow-success/30",
  warning: "bg-warning/90 text-black border-warning shadow-sm shadow-warning/30",
  danger: "bg-danger/90 text-white border-danger shadow-sm shadow-danger/30",
  neutral: "bg-surface-3 text-text-secondary border-border",
};

interface BadgeProps {
  variant?: Variant;
  prominent?: boolean;
  children: React.ReactNode;
  className?: string;
  title?: string;
}

export function Badge({ variant = "neutral", prominent, children, className, title }: BadgeProps) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
        prominent ? prominentVariantStyles[variant] : variantStyles[variant],
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
  const label = score >= 0.9 ? "High" : score >= 0.75 ? "Medium" : "Low";
  const Icon = score >= 0.9 ? Check : score >= 0.75 ? AlertTriangle : XCircle;
  return (
    <span title={`${label} confidence match (${pct}%) — how closely this mod matches the Nexus entry`}>
      <Badge variant={variant}><Icon size={10} className="mr-0.5" />{pct}%</Badge>
    </span>
  );
}
