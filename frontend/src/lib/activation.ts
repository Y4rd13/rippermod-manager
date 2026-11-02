import type { KeyboardEvent } from "react";

/**
 * Makes a clickable non-button element (a table row, a card) reachable and usable from the
 * keyboard: it joins the Tab order, and Enter or Space on the element itself activates it.
 * Keys pressed in an inner control (a checkbox, a menu button) are left to that control.
 */
export function activationProps(onActivate: () => void): {
  tabIndex: 0;
  onClick: () => void;
  onKeyDown: (e: KeyboardEvent) => void;
} {
  return {
    tabIndex: 0,
    onClick: onActivate,
    onKeyDown: (e) => {
      if (e.target !== e.currentTarget) return;
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onActivate();
      }
    },
  };
}
