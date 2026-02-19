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

function handleNxmLink(link: NxmLink, deps: NxmHandlerDeps) {
  const games = deps.getGames();
  if (!games) {
    toast.error("NXM link received", "Games not loaded yet — try again");
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
  let cancelled = false;
  let unlisten: (() => void) | undefined;
  const window = getCurrentWebviewWindow();

  listen<string>("nxm-link", (event) => {
    if (cancelled) return;
    window.setFocus();
    const link = parseNxmUrl(event.payload);
    if (link) {
      handleNxmLink(link, deps);
    } else {
      toast.error("Invalid NXM link", "Could not parse the download URL");
    }
  }).then((fn) => {
    if (cancelled) {
      fn();
    } else {
      unlisten = fn;
    }
  });

  // Check for cold-start URLs via the deep-link plugin
  import("@tauri-apps/plugin-deep-link").then(({ getCurrent }) => {
    if (cancelled) return;
    getCurrent().then((urls) => {
      if (cancelled || !urls || urls.length === 0) return;
      for (const url of urls) {
        const link = parseNxmUrl(url);
        if (link) {
          handleNxmLink(link, deps);
          break;
        }
      }
    });
  });

  return () => {
    cancelled = true;
    unlisten?.();
  };
}
