// Session/CSRF material stays in memory; the session cookie is HttpOnly.
export let csrf = "";
export let operator = false;
export let localMode = true;
export async function refreshAuth() {
  const response = await fetch("/api/auth/session");
  if (!response.ok) throw Error("Authentication service unavailable");
  const state = await response.json();
  localMode = state.mode === "local";
  csrf = state.csrf;
  operator = state.role === "operator";
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
    return nativeFetch(input, { ...init, headers });
  }
  return nativeFetch(input, init);
};
