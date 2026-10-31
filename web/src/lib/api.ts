// The console signs in with the admin password; the session lives in an HttpOnly cookie that no
// script can read (docs/adr/0001). The browser sends the Origin header on writes, which the
// service checks. Memory text is still untrusted: render it as text only.
import { toast } from "sonner";

export class AuthError extends Error {}

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

let onUnauthorized: () => void = () => {};

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

async function request<T>(path: string, init: { method?: string; body?: unknown }): Promise<{ status: number; ok: boolean; payload: { ok?: boolean; data?: T; error?: string } | null }> {
  const hasBody = init.body !== undefined;
  const res = await fetch(new URL("/api/v1" + path, window.location.origin), {
    method: init.method ?? "GET",
    credentials: "same-origin",
    headers: hasBody ? { "Content-Type": "application/json" } : {},
    body: hasBody ? JSON.stringify(init.body) : undefined,
  });
  let payload: { ok?: boolean; data?: T; error?: string } | null = null;
  try {
    payload = await res.json();
  } catch {
    // non-JSON error body
  }
  return { status: res.status, ok: res.ok, payload };
}

/** A data or settings call; a lost session sends the person back to sign in. */
export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const { status, ok, payload } = await request<T>(path, init);
  if (status === 401) {
    onUnauthorized();
    throw new AuthError("登录已失效，请重新登录。");
  }
  if (!ok || !payload || payload.ok === false) {
    throw new ApiError(payload?.error || `请求失败（HTTP ${status}）`, status);
  }
  return payload.data as T;
}

/** A sign-in call: errors come back as messages, never as a redirect to sign in. */
export async function consoleApi<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const { status, ok, payload } = await request<T>(path, init);
  if (!ok || !payload || payload.ok === false) {
    throw new ApiError(payload?.error || `请求失败（HTTP ${status}）`, status);
  }
  return payload.data as T;
}

export const enc = encodeURIComponent;

/** Report a failed request as an error toast; an auth failure already returned to sign-in. */
export function failed(error: unknown) {
  if (!(error instanceof AuthError)) toast.error(error instanceof Error ? error.message : String(error));
}
