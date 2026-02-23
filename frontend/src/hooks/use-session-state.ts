import { useState, useCallback, useEffect, useRef } from "react";

/**
 * Like useState but persists to sessionStorage (survives tab changes, lost on
 * window close).  Falls back to plain useState if storage is unavailable.
 */
export function useSessionState<T>(key: string, initialValue: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = sessionStorage.getItem(key);
      return stored !== null ? (JSON.parse(stored) as T) : initialValue;
    } catch {
      return initialValue;
    }
  });

  // Sync state when key changes without remount (e.g. gameName change).
  const prevKey = useRef(key);
  useEffect(() => {
    if (prevKey.current === key) return;
    prevKey.current = key;
    try {
      const stored = sessionStorage.getItem(key);
      setValue(stored !== null ? (JSON.parse(stored) as T) : initialValue);
    } catch {
      setValue(initialValue);
    }
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const resolved = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
        try {
          sessionStorage.setItem(key, JSON.stringify(resolved));
        } catch {
          // quota exceeded — degrade silently
        }
        return resolved;
      });
    },
    [key],
  );

  return [value, set] as const;
}
