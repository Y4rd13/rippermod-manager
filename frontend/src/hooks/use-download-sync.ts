import { useEffect, useRef } from "react";

import { useDownloadJobs } from "@/hooks/queries";
import { useDownloadStore } from "@/stores/download-store";

export function useDownloadSync(gameName: string | null) {
  const syncJobs = useDownloadStore((s) => s.syncJobs);
  const reset = useDownloadStore((s) => s.reset);
  const prevGameRef = useRef(gameName);

  const { data: polledJobs } = useDownloadJobs(gameName ?? "");

  useEffect(() => {
    if (prevGameRef.current !== gameName) {
      reset();
      prevGameRef.current = gameName;
    }
  }, [gameName, reset]);

  useEffect(() => {
    if (polledJobs && gameName) {
      syncJobs(polledJobs);
    }
  }, [polledJobs, gameName, syncJobs]);
}
