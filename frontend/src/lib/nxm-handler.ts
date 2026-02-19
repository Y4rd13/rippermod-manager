import { listen } from "@tauri-apps/api/event";
import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";

import type { DownloadRequest, Game } from "@/types/api";
import { toast } from "@/stores/toast-store";

export interface NxmLink {
  domain: string;
  modId: number;
  fileId: number;
  key: string;
  expires: number;
}

export function parseNxmUrl(raw: string): NxmLink | null {
  // nxm://cyberpunk2077/mods/107/files/123?key=abc123&expires=1234567890
  try {
    const url = new URL(raw);
    if (url.protocol !== "nxm:") return null;

    const domain = url.hostname;
    const segments = url.pathname.split("/").filter(Boolean);
    // Expected: ["mods", "<modId>", "files", "<fileId>"]
    if (segments.length < 4 || segments[0] !== "mods" || segments[2] !== "files") return null;

    const modId = Number(segments[1]);
    const fileId = Number(segments[3]);
    if (Number.isNaN(modId) || Number.isNaN(fileId)) return null;

    const key = url.searchParams.get("key") ?? "";
    const expires = Number(url.searchParams.get("expires") ?? "0");

    if (!key || !expires) return null;

    return { domain, modId, fileId, key, expires };
  } catch {
    return null;
  }
}

interface NxmHandlerDeps {
  getGames: () => Game[] | undefined;
  startDownload: (vars: { gameName: string; data: DownloadRequest }) => void;
  navigate: (path: string) => void;
}

const RETRY_INTERVAL_MS = 500;
const MAX_RETRIES = 10;

function handleNxmLink(
  link: NxmLink,
  deps: NxmHandlerDeps,
  ctx: { cancelled: boolean; retryTimers: Set<ReturnType<typeof setTimeout>> },
  retries = 0,
) {
  if (ctx.cancelled) return;

  const games = deps.getGames();
  if (!games) {
    if (retries < MAX_RETRIES) {
      const timer = setTimeout(() => {
        ctx.retryTimers.delete(timer);
        handleNxmLink(link, deps, ctx, retries + 1);
      }, RETRY_INTERVAL_MS);
      ctx.retryTimers.add(timer);
      return;
    }
    toast.error("NXM link failed", "Games not loaded — please try again");
    return;
  }

  const game = games.find((g) => g.domain_name === link.domain);
  if (!game) {
    toast.error("NXM link error", `No game configured for "${link.domain}"`);
    return;
  }

  deps.navigate(`/games/${game.name}`);
  deps.startDownload({
    gameName: game.name,
    data: {
      nexus_mod_id: link.modId,
      nexus_file_id: link.fileId,
      nxm_key: link.key,
      nxm_expires: link.expires,
    },
  });
}

export function setupNxmHandler(deps: NxmHandlerDeps): () => void {
  const ctx = { cancelled: false, retryTimers: new Set<ReturnType<typeof setTimeout>>() };
  let unlisten: (() => void) | undefined;
  const window = getCurrentWebviewWindow();

  listen<string>("nxm-link", (event) => {
    if (ctx.cancelled) return;
    window.setFocus();
    const link = parseNxmUrl(event.payload);
    if (link) {
      handleNxmLink(link, deps, ctx);
    } else {
      toast.error("Invalid NXM link", "Could not parse the download URL");
    }
  })
    .then((fn) => {
      if (ctx.cancelled) {
        fn();
      } else {
        unlisten = fn;
      }
    })
    .catch(() => {
      /* listen unavailable outside Tauri */
    });

  // Check for cold-start URLs via the deep-link plugin
  import("@tauri-apps/plugin-deep-link")
    .then(({ getCurrent }) => {
      if (ctx.cancelled) return;
      getCurrent()
        .then((urls) => {
          if (ctx.cancelled || !urls || urls.length === 0) return;
          for (const url of urls) {
            const link = parseNxmUrl(url);
            if (link) {
              handleNxmLink(link, deps, ctx);
              break;
            }
          }
        })
        .catch(() => {
          /* getCurrent unavailable */
        });
    })
    .catch(() => {
      /* deep-link plugin unavailable */
    });

  return () => {
    ctx.cancelled = true;
    unlisten?.();
    for (const timer of ctx.retryTimers) clearTimeout(timer);
    ctx.retryTimers.clear();
  };
}
