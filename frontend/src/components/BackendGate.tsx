import { useEffect, useState, type ReactNode } from "react";

import { Loader2, ServerCrash } from "lucide-react";

import { Button } from "@/components/ui/Button";

const HEALTH_URL = "http://127.0.0.1:8425/health";
const POLL_INTERVAL = 1000;
const MAX_DEV_POLLS = 60;

type Status = "waiting" | "ready" | "failed";

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
              setStatus("ready");
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
