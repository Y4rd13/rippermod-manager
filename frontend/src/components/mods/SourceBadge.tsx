import { cn } from "@/lib/utils";

const SOURCE_STYLES: Record<string, { label: string; cls: string }> = {
  installed: { label: "Installed", cls: "bg-success/15 text-success" },
  correlation: { label: "Matched", cls: "bg-warning/15 text-warning" },
  endorsed: { label: "Endorsed", cls: "bg-accent/15 text-accent" },
  tracked: { label: "Tracked", cls: "bg-info/15 text-info" },
};

export function SourceBadge({ source }: { source: string }) {
  const style = SOURCE_STYLES[source] ?? { label: source, cls: "bg-accent/15 text-accent" };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium",
        style.cls,
      )}
    >
      {style.label}
    </span>
  );
}
