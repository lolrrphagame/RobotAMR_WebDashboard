import { localMode } from "../auth";
import { useState } from "react";
export function OperatorSession({ operator }: { operator: boolean }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const submit = async (logout = false) => {
    try {
      const response = await fetch(
        logout ? "/api/auth/logout" : "/api/auth/login",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: logout ? undefined : JSON.stringify({ password }),
        },
      );
      setPassword("");
      if (!response.ok)
        throw Error(
          response.status === 429
            ? "Login rate exceeded; retry later."
            : "Authentication failed",
        );
      location.reload();
    } catch (e) {
      setError(String(e));
    }
  };
  return (
    <div className="simulation-banner">
      <strong>{operator ? "Authorized operator" : "Read-only observer"}</strong>
      {operator && localMode ? (
        <span>Loopback development</span>
      ) : operator ? (
        <button onClick={() => void submit(true)}>Sign out</button>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <label>
            Operator password{" "}
            <input
              aria-label="Operator password"
              type="password"
              autoComplete="current-password"
              value={password}
              maxLength={256}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button type="submit">Sign in</button>
        </form>
      )}
      {error && <span role="alert">{error}</span>}
    </div>
  );
}
