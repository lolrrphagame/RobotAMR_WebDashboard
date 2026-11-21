// Session/CSRF material stays in memory; the session cookie is HttpOnly.
export let csrf = "";
export let operator = false;
export let localMode = true;
export type Session = {
  mode: "local" | "lan";
  authenticated: boolean;
  role: "operator" | "observer" | null;
  username: string | null;
  csrf: string;
};
export function clearAuth() {
  csrf = "";
  operator = false;
}
export async function refreshAuth() {
  const response = await fetch("/api/auth/session");
  if (!response.ok) throw Error("Authentication service unavailable");
  const state = (await response.json()) as Session;
  localMode = state.mode === "local";
  csrf = state.csrf;
  operator = state.role === "operator";
  if (state.mode === "lan" && !state.authenticated)
    window.dispatchEvent(new Event("authentication-required"));
  return state;
}
const nativeFetch = window.fetch.bind(window);
window.fetch = async (input, init) => {
  const url = new URL(
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.href
        : input.url,
    location.href,
  );
  const method = (
    init?.method ?? (input instanceof Request ? input.method : "GET")
  ).toUpperCase();
  if (
    url.origin === location.origin &&
    url.pathname.startsWith("/api/") &&
    !["GET", "HEAD", "OPTIONS"].includes(method)
  ) {
    const headers = new Headers(init?.headers);
    if (csrf) headers.set("X-CSRF-Token", csrf);
    const response = await nativeFetch(input, { ...init, headers });
    if (response.status === 401 && url.pathname !== "/api/auth/login")
      window.dispatchEvent(new Event("authentication-required"));
    return response;
  }
  const response = await nativeFetch(input, init);
  if (
    url.origin === location.origin &&
    url.pathname.startsWith("/api/") &&
    response.status === 401
  )
    window.dispatchEvent(new Event("authentication-required"));
  return response;
};
