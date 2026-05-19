import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useReducer } from "react";

import { api } from "@/lib/api-client";
import type {
  CollectionActionResult,
  CollectionInstallRequest,
  CollectionPreview,
  CollectionProgressEvent,
  CollectionStatus,
  CollectionUpdate,
} from "@/types/api";

const previewPath = (gameName: string, slug: string, revision: number) =>
  `/api/v1/games/${encodeURIComponent(gameName)}/collections/${encodeURIComponent(slug)}/revision/${revision}/preview`;

const installPath = (gameName: string) =>
  `/api/v1/games/${encodeURIComponent(gameName)}/collections/install`;

const listPath = (gameName: string) =>
  `/api/v1/games/${encodeURIComponent(gameName)}/collections`;

const statusPath = (collectionId: number) =>
  `/api/v1/collections/${collectionId}/status`;

const streamPath = (collectionId: number) =>
  `/api/v1/collections/${collectionId}/stream`;

/**
 * Fetch the install-preview payload for a Collection revision. Premium check
 * happens server-side; this endpoint works for everyone.
 */
export function useCollectionPreview(
  gameName: string | null,
  slug: string | null,
  revision: number | null,
) {
  return useQuery<CollectionPreview>({
    queryKey: ["collection-preview", gameName, slug, revision],
    queryFn: () => api.get(previewPath(gameName!, slug!, revision!)),
    enabled: !!gameName && !!slug && revision != null,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

/**
 * Kick off a Collection install. Returns ``CollectionStatus`` immediately
 * (the backend spawns a background runner). UI should switch to the progress
 * view and subscribe to ``useCollectionStream`` for live updates.
 *
 * Errors surface as plain ``Error`` with the backend's HTTP detail when
 * possible (e.g. premium-required = 400, in-progress = 409).
 */
export function useInstallCollection(gameName: string | null) {
  const qc = useQueryClient();
  return useMutation<CollectionStatus, Error, CollectionInstallRequest>({
    mutationFn: (body) => api.post<CollectionStatus>(installPath(gameName!), body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["collections-list", gameName] });
    },
  });
}

export function useCollectionList(gameName: string | null) {
  return useQuery<CollectionStatus[]>({
    queryKey: ["collections-list", gameName],
    queryFn: () => api.get(listPath(gameName!)),
    enabled: !!gameName,
  });
}

export function useCollectionStatus(collectionId: number | null) {
  return useQuery<CollectionStatus>({
    queryKey: ["collection-status", collectionId],
    queryFn: () => api.get(statusPath(collectionId!)),
    enabled: collectionId != null,
    // Polling is a fallback for clients that drop the SSE stream; the live
    // ``useCollectionStream`` hook is the primary source of progress updates.
    refetchInterval: (q) => {
      const data = q.state.data as CollectionStatus | undefined;
      if (!data) return 2_000;
      return ["installed", "partial", "failed", "cancelled"].includes(data.status)
        ? false
        : 2_000;
    },
  });
}

/**
 * Subscribe to the SSE progress stream for an in-flight Collections install.
 *
 * The first event the backend emits is the initial ``CollectionStatus``
 * snapshot; subsequent events are ``CollectionProgressEvent``s as the
 * runner makes progress. We discriminate at the consumer side by checking
 * for the ``phase`` field (only present on progress events).
 */
interface StreamState {
  // Key kept in state so the reducer can reset cleanly when collectionId
  // flips, without an explicit setState-in-effect (which the lint rule
  // forbids — it would cause a cascading render on every input change).
  collectionId: number | null;
  // Only the latest event is ever read by the UI — historical events would
  // cost O(n²) array copies for data nothing consumes. Keep one slot.
  latestEvent: CollectionProgressEvent | null;
  closed: boolean;
}

type StreamAction =
  | { type: "reset"; collectionId: number | null }
  | { type: "event"; collectionId: number; event: CollectionProgressEvent }
  | { type: "close"; collectionId: number };

function streamReducer(state: StreamState, action: StreamAction): StreamState {
  switch (action.type) {
    case "reset":
      if (state.collectionId === action.collectionId) return state;
      return { collectionId: action.collectionId, latestEvent: null, closed: false };
    case "event":
      if (state.collectionId !== action.collectionId) return state;
      return { ...state, latestEvent: action.event };
    case "close":
      if (state.collectionId !== action.collectionId) return state;
      return { ...state, closed: true };
  }
}

export function useCollectionStream(collectionId: number | null) {
  const [state, dispatch] = useReducer(streamReducer, {
    collectionId,
    latestEvent: null,
    closed: false,
  });

  useEffect(() => {
    dispatch({ type: "reset", collectionId });
    if (collectionId == null) return;

    // ``EventSource`` doesn't go through the api-client wrapper (no auth
    // needed since backend listens on localhost), but we reuse the same
    // base URL so VITE_API_URL overrides apply uniformly.
    const url = `${api.baseUrl}${streamPath(collectionId)}`;
    const es = new EventSource(url);

    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data) as Partial<CollectionProgressEvent>;
        if (payload && typeof payload.phase === "string") {
          dispatch({
            type: "event",
            collectionId,
            event: payload as CollectionProgressEvent,
          });
          if (payload.phase === "done" || payload.phase === "error") {
            dispatch({ type: "close", collectionId });
            es.close();
          }
        }
        // Non-progress payloads (e.g. the initial status snapshot) are
        // ignored here; the parallel ``useCollectionStatus`` query owns that.
      } catch {
        // Malformed event -- drop it; the polling fallback will eventually
        // catch us up to the right state.
      }
    };

    es.addEventListener("close", () => {
      dispatch({ type: "close", collectionId });
      es.close();
    });

    es.onerror = () => {
      // Browser auto-retries on network error; we only flip ``closed`` once
      // the install hits a terminal phase to avoid showing a stuck UI.
      if (es.readyState === EventSource.CLOSED) {
        dispatch({ type: "close", collectionId });
      }
    };

    return () => {
      es.close();
    };
  }, [collectionId]);

  return { latestEvent: state.latestEvent, closed: state.closed };
}

/**
 * Uninstall a collection: drops the InstalledCollection row + uninstalls
 * every mod that was tagged with it. Backend cascades + runs a final deploy.
 */
export function useUninstallCollection(gameName: string | null) {
  const qc = useQueryClient();
  return useMutation<{ removed_mods: number; failed_mods: number }, Error, number>({
    mutationFn: (collectionId) =>
      api.delete<{ removed_mods: number; failed_mods: number }>(
        `/api/v1/collections/${collectionId}`,
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["collections-list", gameName] });
      void qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
    },
  });
}

/**
 * Skip the mod a free-tier orchestrator is currently waiting on. Wakes the
 * orchestrator with a ``CollectionModSkipped`` signal so the mod gets
 * counted as skipped (not failed) and the install advances to the next
 * entry without restarting the whole batch.
 */
export function useSkipPendingNxm(collectionId: number | null) {
  return useMutation<
    CollectionActionResult,
    Error,
    { nexusModId: number; nexusFileId: number }
  >({
    mutationFn: ({ nexusModId, nexusFileId }) =>
      api.post<CollectionActionResult>(
        `/api/v1/collections/${collectionId}/skip-pending-nxm`,
        { nexus_mod_id: nexusModId, nexus_file_id: nexusFileId },
      ),
  });
}

/**
 * Cancel an in-flight Collections install. Marks the row as ``cancelled``
 * via the orchestrator's ``CancelledError`` handler. To also remove the
 * row + uninstall already-completed mods, call ``useUninstallCollection``
 * afterwards.
 */
export function useCancelCollectionInstall(collectionId: number | null) {
  const qc = useQueryClient();
  return useMutation<CollectionActionResult, Error, void>({
    mutationFn: () =>
      api.post<CollectionActionResult>(`/api/v1/collections/${collectionId}/cancel`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["collection-status", collectionId] });
    },
  });
}

/**
 * Ask Nexus for the latest published revision of every installed
 * collection in this game, and persist the result on each row. The
 * resulting list is the per-collection summary; the UI also invalidates
 * ``collections-list`` so the cached ``latest_known_revision_number``
 * fields refresh.
 */
export function useCheckCollectionUpdates(gameName: string | null) {
  const qc = useQueryClient();
  return useMutation<CollectionUpdate[], Error, void>({
    mutationFn: () =>
      api.post<CollectionUpdate[]>(
        `/api/v1/games/${encodeURIComponent(gameName!)}/collections/check-updates`,
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["collections-list", gameName] });
    },
  });
}
