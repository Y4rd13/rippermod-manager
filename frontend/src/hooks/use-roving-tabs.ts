import {
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
} from "react";

type TabProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  ref: (el: HTMLButtonElement | null) => void;
};

/**
 * WAI-ARIA tabs with a roving tabindex: only the active tab is in the Tab order, the arrow
 * keys move focus between tabs (wrapping), Home and End jump to the ends, and Enter or Space
 * (the button's own click) selects. Tab `k` controls the panel with id `tabpanel-<k>`.
 * When the active tab changes, it is scrolled into view inside an overflowing strip.
 */
export function useRovingTabs<K extends string>(
  keys: readonly K[],
  active: K,
  onSelect: (k: K) => void,
): {
  tabListProps: HTMLAttributes<HTMLElement>;
  getTabProps: (k: K) => TabProps;
} {
  const tabs = useRef(new Map<K, HTMLButtonElement>());
  const previous = useRef(active);

  useEffect(() => {
    if (previous.current === active) return;
    previous.current = active;
    tabs.current.get(active)?.scrollIntoView?.({ inline: "nearest", block: "nearest" });
  }, [active]);

  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLElement>) => {
      const current = keys.findIndex((k) => tabs.current.get(k) === document.activeElement);
      if (current === -1) return;
      let next: number;
      switch (e.key) {
        case "ArrowRight":
          next = (current + 1) % keys.length;
          break;
        case "ArrowLeft":
          next = (current - 1 + keys.length) % keys.length;
          break;
        case "Home":
          next = 0;
          break;
        case "End":
          next = keys.length - 1;
          break;
        default:
          return;
      }
      e.preventDefault();
      const el = tabs.current.get(keys[next]);
      el?.focus();
      el?.scrollIntoView?.({ inline: "nearest", block: "nearest" });
    },
    [keys],
  );

  const getTabProps = (k: K): TabProps => ({
    ref: (el) => {
      if (el) tabs.current.set(k, el);
      else tabs.current.delete(k);
    },
    role: "tab",
    id: `tab-${k}`,
    type: "button",
    "aria-selected": k === active,
    "aria-controls": `tabpanel-${k}`,
    tabIndex: k === active ? 0 : -1,
    onClick: () => onSelect(k),
  });

  return { tabListProps: { role: "tablist", onKeyDown }, getTabProps };
}
