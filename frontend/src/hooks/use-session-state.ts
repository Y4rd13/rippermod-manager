import { useState, useCallback } from "react";

function readStorage<T>(key: string, fallback: T): T {
  try {
    const stored = sessionStorage.getItem(key);
    return stored !== null ? (JSON.parse(stored) as T) : fallback;
  } catch {
    return fallback;
  }
}

/**
 * Like useState but persists to sessionStorage (survives tab changes, lost on
 * window close).  Falls back to plain useState if storage is unavailable.
 */
export function useSessionState<T>(key: string, initialValue: T) {
  const [state, setState] = useState({ key, value: readStorage(key, initialValue) });

  // Adjust state during render when key changes (React-recommended pattern).
  if (state.key !== key) {
    setState({ key, value: readStorage(key, initialValue) });
  }

  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      setState((prev) => {
        const resolved = typeof next === "function" ? (next as (p: T) => T)(prev.value) : next;
        try {
          sessionStorage.setItem(key, JSON.stringify(resolved));
        } catch {
          // quota exceeded — degrade silently
        }
        return { key, value: resolved };
      });
    },
    [key],
  );

  return [state.value, set] as const;
}
