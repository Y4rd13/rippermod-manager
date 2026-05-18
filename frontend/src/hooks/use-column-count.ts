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
  const [count, setCount] = useState(() => getColumnCount(variant));

  useEffect(() => {
    const md = window.matchMedia("(min-width: 768px)");
    const xl = window.matchMedia("(min-width: 1280px)");

    const update = () => setCount(getColumnCount(variant));
    update();

    md.addEventListener("change", update);
    xl.addEventListener("change", update);
    return () => {
      md.removeEventListener("change", update);
      xl.removeEventListener("change", update);
    };
  }, [variant]);

  return count;
}
