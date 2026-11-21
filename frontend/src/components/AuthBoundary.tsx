import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Bot, LockKeyhole, ShieldCheck } from "lucide-react";
import { clearAuth, refreshAuth, localMode } from "../auth";
import type { Session } from "../auth";

const SessionContext = createContext<{
  session: Session;
  signOut: () => Promise<void>;
} | null>(null);
export function useSession() {
  const context = useContext(SessionContext);
  if (!context) throw Error("Authenticated session required");
  return context;
}

export function AuthBoundary({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const forcedOut = useRef(false);
  const loseSession = () => {
    clearAuth();
    setSession({
      mode: "lan",
      authenticated: false,
      username: null,
      role: null,
      csrf: "",
    });
  };
  useEffect(() => {
    let disposed = false;
    const check = async () => {
      if (forcedOut.current) return;
      try {
        const state = await refreshAuth();
        if (!disposed && !forcedOut.current) {
          setSession(state);
          setError("");
        }
      } catch {
        if (!disposed) {
          if (!localMode) loseSession();
          setError(
            "Authentication service unavailable. Check the server connection and retry.",
          );
        }
      }
    };
    const expired = () => {
      if (!disposed) loseSession();
    };
    window.addEventListener("authentication-required", expired);
    const restored = (event: PageTransitionEvent) => {
      if (event.persisted) {
        clearAuth();
        setSession(null);
        void check();
      }
    };
    window.addEventListener("pageshow", restored);
    void check();
    const interval = setInterval(() => void check(), 5000);
    return () => {
      disposed = true;
      clearInterval(interval);
      window.removeEventListener("authentication-required", expired);
      window.removeEventListener("pageshow", restored);
    };
  }, []);
  const signIn = async () => {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      setPassword("");
      if (!response.ok)
        throw Error(
          response.status === 429
            ? "Too many sign-in attempts. Retry in one minute."
            : "Invalid username or password.",
        );
      const state = await refreshAuth();
      if (!state.authenticated)
        throw Error(
          "Session could not be established. Check HTTPS and cookie settings.",
        );
      forcedOut.current = false;
      setSession(state);
    } catch (cause) {
      setPassword("");
      setError(
        cause instanceof Error
          ? cause.message
          : "Sign-in failed. Please retry.",
      );
    } finally {
      setBusy(false);
    }
  };
  const signOut = async () => {
    // Unmount all private views and close sockets immediately, even during a network failure.
    forcedOut.current = true;
    const response = fetch("/api/auth/logout", { method: "POST" });
    loseSession();
    setPassword("");
    try {
      if (!(await response).ok) throw Error();
    } catch {
      setError(
        "Server logout could not be confirmed. Reconnect and sign in to retry logout; this browser has cleared its dashboard data.",
      );
    }
  };
  if (session?.authenticated)
    return (
      <SessionContext.Provider value={{ session, signOut }}>
        {children}
      </SessionContext.Provider>
    );
  return (
    <main className="login-shell">
      <section className="login-card" aria-label="Dashboard authentication">
        <div className="login-brand">
          <span className="brand-symbol">
            <Bot size={30} />
          </span>
          <div>
            PBL4<span className="brand-sub">ROBOTICS LAB</span>
          </div>
        </div>
        <span className="eyebrow">SECURE MISSION CONTROL</span>
        <h1>Sign in to your workspace</h1>
        <p className="muted">
          Authenticated access for Operators and read-only Observers.
        </p>
        {!session && !error ? (
          <p role="status">Checking secure session…</p>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void signIn();
            }}
          >
            <label htmlFor="login-username">Username</label>
            <input
              id="login-username"
              autoComplete="username"
              maxLength={64}
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              disabled={busy}
            />
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              maxLength={256}
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={busy}
            />
            <button type="submit" className="primary" disabled={busy}>
              <LockKeyhole size={16} />
              {busy ? "Signing in…" : "Sign In"}
            </button>
          </form>
        )}
        {error && (
          <p className="login-error" role="alert">
            {error}
          </p>
        )}
        <div className="login-safety">
          <ShieldCheck size={17} />
          <span>
            SIMULATION ONLY · Private HTTPS access
            <br />
            Accounts are provisioned by the lab administrator.
          </span>
        </div>
      </section>
    </main>
  );
}
