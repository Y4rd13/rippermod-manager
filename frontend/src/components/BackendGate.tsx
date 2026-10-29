import { useEffect, useState, type ReactNode } from "react";

import { Loader2, ServerCrash } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { getApiToken, TOKEN_HEADER } from "@/lib/api-client";

const HEALTH_URL = "http://127.0.0.1:8425/health";
const DEEP_HEALTH_URL = "http://127.0.0.1:8425/health/deep";
const POLL_INTERVAL = 1000;
const MAX_DEV_POLLS = 60;

type Status = "waiting" | "ready" | "failed" | "token-rejected";

/** Dev only: a 401 here means the backend on 8425 was started with another token. */
async function tokenIsRejected(): Promise<boolean> {
  try {
    const token = await getApiToken();
    const res = await fetch(DEEP_HEALTH_URL, { headers: { [TOKEN_HEADER]: token } });
    return res.status === 401;
  } catch {
    // No token available, or the request failed: let the app surface it.
    return false;
  }
}

function useBackendStatus(): Status {
  const [status, setStatus] = useState<Status>("waiting");

  useEffect(() => {
    const isDev = import.meta.env.DEV;

    if (isDev) {
      let cancelled = false;
      let polls = 0;

      const poll = async () => {
        while (!cancelled && polls < MAX_DEV_POLLS) {
          try {
            const res = await fetch(HEALTH_URL);
            if (res.ok) {
              const rejected = await tokenIsRejected();
              if (!cancelled) setStatus(rejected ? "token-rejected" : "ready");
              return;
            }
          } catch {
            // backend not up yet
          }
          polls++;
          await new Promise((r) => setTimeout(r, POLL_INTERVAL));
        }
        if (!cancelled) setStatus("failed");
      };

      poll();
      return () => { cancelled = true; };
    }

    // Production: listen for Tauri events
    let cancelled = false;
    let unlisten: (() => void)[] = [];

    (async () => {
      const { listen } = await import("@tauri-apps/api/event");
      if (cancelled) return;

      unlisten = await Promise.all([
        listen("backend-ready", () => setStatus("ready")),
        listen("backend-startup-failed", () => setStatus("failed")),
        listen("backend-crashed", () => setStatus("failed")),
      ]);
    })();

    return () => {
      cancelled = true;
      unlisten.forEach((u) => u());
    };
  }, []);

  return status;
}

export function BackendGate({ children }: { children: ReactNode }) {
  const status = useBackendStatus();

  if (status === "ready") {
    return <>{children}</>;
  }

  if (status === "token-rejected") {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-surface-0 text-center">
        <ServerCrash className="h-12 w-12 text-danger" />
        <h1 className="text-xl font-semibold text-text-primary">
          Token rejected: another backend is running on port 8425.
        </h1>
        <p className="max-w-md text-sm text-text-secondary">
          Stop it, or start the backend and the frontend with the same RMM_API_TOKEN
          (VITE_API_TOKEN for Vite alone).
        </p>
        <Button variant="secondary" onClick={() => window.location.reload()}>
          Retry
        </Button>
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-surface-0 text-center">
        <ServerCrash className="h-12 w-12 text-danger" />
        <h1 className="text-xl font-semibold text-text-primary">
          Backend failed to start
        </h1>
        <p className="max-w-md text-sm text-text-secondary">
          {import.meta.env.DEV
            ? "Make sure the backend server is running: cd backend && uv run uvicorn rippermod_manager.main:app --port 8425"
            : "The application backend could not be started. Try restarting the application."}
        </p>
        <Button variant="secondary" onClick={() => window.location.reload()}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col items-center justify-center gap-3 bg-surface-0">
      <Loader2 className="h-8 w-8 animate-spin text-accent" />
      <p className="text-sm text-text-secondary">Starting backend...</p>
    </div>
  );
}
