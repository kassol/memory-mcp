import { toast } from "sonner";

// The access token lives in sessionStorage until the admin password ticket replaces it with a
// session cookie (docs/adr/0001). Memory text is untrusted: render it as text only, never as HTML,
// because an HTML injection here would leak the token.
const TOKEN_KEY = "memory-mcp.access-token";

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

export const getToken = () => sessionStorage.getItem(TOKEN_KEY);
export const setToken = (token: string) => sessionStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => sessionStorage.removeItem(TOKEN_KEY);

export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const token = getToken();
  if (!token) throw new AuthError("未登录");
  const hasBody = init.body !== undefined;
  const res = await fetch(new URL("/api/v1" + path, window.location.origin), {
    method: init.method ?? "GET",
    headers: { Authorization: `Bearer ${token}`, ...(hasBody ? { "Content-Type": "application/json" } : {}) },
    body: hasBody ? JSON.stringify(init.body) : undefined,
  });
  if (res.status === 401 || res.status === 403) {
    clearToken();
    onUnauthorized();
    throw new AuthError("令牌无效，请重新输入。");
  }
  let payload: { ok?: boolean; data?: T; error?: string } | null = null;
  try {
    payload = await res.json();
  } catch {
    // non-JSON error body
  }
  if (!res.ok || !payload || payload.ok === false) {
    throw new ApiError(payload?.error || `请求失败（HTTP ${res.status}）`, res.status);
  }
  return payload.data as T;
}

export const enc = encodeURIComponent;

/** Report a failed request as an error toast; an auth failure already returned to sign-in. */
export function failed(error: unknown) {
  if (!(error instanceof AuthError)) toast.error(error instanceof Error ? error.message : String(error));
}
