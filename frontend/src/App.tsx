import { useEffect, useRef } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router";

import { BackendGate } from "@/components/BackendGate";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { queryClient } from "@/lib/query-client";
import { setupNxmHandler } from "@/lib/nxm-handler";
import { router } from "@/router";
import { useGames } from "@/hooks/queries";
import { useStartDownload } from "@/hooks/mutations";
import type { Game, DownloadRequest } from "@/types/api";

function NxmHandler() {
  const { data: games } = useGames();
  const { mutate: startDownload } = useStartDownload();

  const gamesRef = useRef<Game[] | undefined>(games);
  const downloadRef = useRef(startDownload);

  useEffect(() => {
    gamesRef.current = games;
  }, [games]);

  useEffect(() => {
    downloadRef.current = startDownload;
  }, [startDownload]);

  useEffect(() => {
    return setupNxmHandler({
      getGames: () => gamesRef.current,
      startDownload: (vars: { gameName: string; data: DownloadRequest }) =>
        downloadRef.current(vars),
      navigate: (path: string) => router.navigate(path),
    });
  }, []);

  return null;
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BackendGate>
          <NxmHandler />
          <RouterProvider router={router} />
        </BackendGate>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
