import { useSession } from "./AuthBoundary";
export function OperatorSession({ operator }: { operator: boolean }) {
  const { session, signOut } = useSession();
  return (
    <div className="simulation-banner">
      <strong>{operator ? "Authorized operator" : "Read-only observer"}</strong>
      <span>{session.username}</span>
      {session.mode === "local" ? (
        <span>Loopback development</span>
      ) : (
        <button onClick={() => void signOut()}>Sign out</button>
      )}
    </div>
  );
}
