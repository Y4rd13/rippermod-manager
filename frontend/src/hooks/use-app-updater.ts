import { useCallback, useEffect, useRef } from "react";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";

import { toast } from "@/stores/toast-store";
import { useUpdaterStore } from "@/stores/updater-store";

export function useAppUpdater() {
  const {
    status,
    updateInfo,
    error,
    downloadProgress,
    setStatus,
    setUpdateInfo,
    setError,
    setDownloadProgress,
  } = useUpdaterStore();

  const updateRef = useRef<Update | null>(null);

  const checkForUpdate = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (status === "checking" || status === "downloading") return;

      setStatus("checking");
      setError(null);

      try {
        const update = await check();

        if (update) {
          updateRef.current = update;
          setUpdateInfo({
            version: update.version,
            date: update.date ?? null,
            body: update.body ?? null,
          });
          setStatus("available");
          if (!opts?.silent) {
            toast.info("Update available", `Version ${update.version} is ready to download.`);
          }
        } else {
          updateRef.current = null;
          setUpdateInfo(null);
          setStatus("up-to-date");
          if (!opts?.silent) {
            toast.success("Up to date", "You are running the latest version.");
          }
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Update check failed";
        setError(msg);
        setStatus("error");
        if (!opts?.silent) {
          toast.error("Update check failed", msg);
        }
      }
    },
    [status, setStatus, setError, setUpdateInfo],
  );

  const downloadAndInstall = useCallback(async () => {
    const update = updateRef.current;
    if (!update) return;

    setStatus("downloading");
    setDownloadProgress(0);

    try {
      let downloaded = 0;
      let contentLength = 0;

      await update.downloadAndInstall((event) => {
        switch (event.event) {
          case "Started":
            contentLength = event.data.contentLength ?? 0;
            break;
          case "Progress":
            downloaded += event.data.chunkLength;
            if (contentLength > 0) {
              setDownloadProgress(Math.round((downloaded / contentLength) * 100));
            }
            break;
          case "Finished":
            setDownloadProgress(100);
            break;
        }
      });

      setStatus("ready");
      toast.success("Update installed", "Restart the application to apply the update.");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Update install failed";
      setError(msg);
      setStatus("error");
      toast.error("Update failed", msg);
    }
  }, [setStatus, setError, setDownloadProgress]);

  const restartApp = useCallback(async () => {
    await relaunch();
  }, []);

  const hasChecked = useRef(false);
  useEffect(() => {
    if (hasChecked.current) return;
    if (import.meta.env.DEV) return;
    hasChecked.current = true;

    const timer = setTimeout(() => {
      void checkForUpdate({ silent: true });
    }, 5000);

    return () => clearTimeout(timer);
  }, [checkForUpdate]);

  return {
    status,
    updateInfo,
    error,
    downloadProgress,
    checkForUpdate,
    downloadAndInstall,
    restartApp,
  };
}
