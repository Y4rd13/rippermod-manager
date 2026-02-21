import { useCallback, useEffect, useRef, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";

import { api } from "@/lib/api-client";
import { toast } from "@/stores/toast-store";
import type { NexusKeyResult, SSOPollResult, SSOStartResult } from "@/types/api";

type SSOState = "idle" | "connecting" | "waiting" | "success" | "error";

interface UseNexusSSOReturn {
  state: SSOState;
  error: string;
  result: NexusKeyResult | null;
  startSSO: () => void;
  cancel: () => void;
}

const POLL_INTERVAL = 2000;

export function useNexusSSO(): UseNexusSSOReturn {
  const [state, setState] = useState<SSOState>("idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState<NexusKeyResult | null>(null);
  const uuidRef = useRef<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const cleanup = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = undefined;
    }
    if (uuidRef.current) {
      api.delete(`/api/v1/nexus/sso/${uuidRef.current}`).catch(() => {});
      uuidRef.current = null;
    }
  }, []);

  useEffect(() => {
    return cleanup;
  }, [cleanup]);

  const startSSO = useCallback(async () => {
    cleanup();
    setState("connecting");
    setError("");
    setResult(null);

    try {
      const data = await api.post<SSOStartResult>("/api/v1/nexus/sso/start");
      uuidRef.current = data.uuid;

      await openUrl(data.authorize_url);
      setState("waiting");
      toast.info("Authorize in browser", "Complete the login in your browser window");

      timerRef.current = setInterval(async () => {
        if (!uuidRef.current) return;
        try {
          const poll = await api.get<SSOPollResult>(
            `/api/v1/nexus/sso/poll/${uuidRef.current}`,
          );
          if (poll.status === "success" && poll.result) {
            clearInterval(timerRef.current);
            timerRef.current = undefined;
            uuidRef.current = null;
            setResult(poll.result);
            setState("success");
            toast.success("Connected", `Signed in as ${poll.result.username}`);
          } else if (poll.status === "error" || poll.status === "expired") {
            clearInterval(timerRef.current);
            timerRef.current = undefined;
            uuidRef.current = null;
            setError(poll.error || "SSO failed");
            setState("error");
            toast.error("SSO failed", poll.error);
          }
        } catch {
          // Transient network error — keep polling
        }
      }, POLL_INTERVAL);
    } catch (e) {
      setState("error");
      setError(e instanceof Error ? e.message : "Failed to start SSO");
    }
  }, [cleanup]);

  const cancel = useCallback(() => {
    cleanup();
    setState("idle");
    setError("");
    setResult(null);
  }, [cleanup]);

  return { state, error, result, startSSO, cancel };
}
