import { useEffect, useState } from "react";

// Must match Tailwind breakpoints: md=768px, xl=1280px
function getColumnCount(): number {
  if (typeof window === "undefined") return 1;
  if (window.matchMedia("(min-width: 1280px)").matches) return 3;
  if (window.matchMedia("(min-width: 768px)").matches) return 2;
  return 1;
}

export function useColumnCount(): number {
  const [count, setCount] = useState(getColumnCount);

  useEffect(() => {
    const md = window.matchMedia("(min-width: 768px)");
    const xl = window.matchMedia("(min-width: 1280px)");

    const update = () => setCount(getColumnCount());

    md.addEventListener("change", update);
    xl.addEventListener("change", update);
    return () => {
      md.removeEventListener("change", update);
      xl.removeEventListener("change", update);
    };
  }, []);

  return count;
}
