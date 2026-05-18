import { useEffect, useState } from "react";

export type ColumnVariant = "card" | "compact";

// Must match Tailwind breakpoints: md=768px, xl=1280px
function getColumnCount(variant: ColumnVariant): number {
  if (typeof window === "undefined") return 1;
  if (variant === "compact") {
    if (window.matchMedia("(min-width: 1280px)").matches) return 6;
    if (window.matchMedia("(min-width: 768px)").matches) return 4;
    return 2;
  }
  if (window.matchMedia("(min-width: 1280px)").matches) return 3;
  if (window.matchMedia("(min-width: 768px)").matches) return 2;
  return 1;
}

export function useColumnCount(variant: ColumnVariant = "card"): number {
  // Tick state only re-renders the component on viewport breakpoint changes;
  // the count itself is derived synchronously from `variant` each render, so
  // switching between variants reflects in the same render with no stale state.
  const [, setTick] = useState(0);

  useEffect(() => {
    const md = window.matchMedia("(min-width: 768px)");
    const xl = window.matchMedia("(min-width: 1280px)");
    const bump = () => setTick((t) => t + 1);
    md.addEventListener("change", bump);
    xl.addEventListener("change", bump);
    return () => {
      md.removeEventListener("change", bump);
      xl.removeEventListener("change", bump);
    };
  }, []);

  return getColumnCount(variant);
}
