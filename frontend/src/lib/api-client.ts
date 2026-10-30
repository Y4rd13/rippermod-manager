import { invoke } from "@tauri-apps/api/core";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8425";

/** Header the backend requires on every `/api/` call and on `/health/deep`. */
export const TOKEN_HEADER = "X-RMM-Token";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(`API error ${status}`);
    this.status = status;
    this.body = body;
  }
}

let tokenPromise: Promise<string> | null = null;

/**
 * The per-launch API token, fetched once and cached.
 *
 * Inside Tauri it comes from the `get_api_token` command (release: generated
 * at startup; debug: `RMM_API_TOKEN` or the backend's `api-token` file).
 * Outside Tauri (Vite alone, a browser, Playwright) it comes from
 * `VITE_API_TOKEN`. A failed lookup is not cached, so the next call retries.
 */
export function getApiToken(): Promise<string> {
  if (!tokenPromise) {
    const pending: Promise<string> =
      "__TAURI_INTERNALS__" in window
        ? invoke<string>("get_api_token")
        : Promise.resolve(import.meta.env.VITE_API_TOKEN ?? "");
    tokenPromise = pending.catch((err: unknown) => {
      tokenPromise = null;
      throw err;
    });
  }
  return tokenPromise;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = await getApiToken();
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
      [TOKEN_HEADER]: token,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  stream: async (
    path: string,
    body?: unknown,
    signal?: AbortSignal,
    method: "GET" | "POST" = "POST",
  ) => {
    const token = await getApiToken();
    const res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: { "Content-Type": "application/json", [TOKEN_HEADER]: token },
      body: method === "POST" && body ? JSON.stringify(body) : undefined,
      signal,
    });
    if (!res.ok) {
      const errorBody = await res.json().catch(() => null);
      throw new ApiError(res.status, errorBody);
    }
    return res;
  },
  baseUrl: BASE_URL,
};
