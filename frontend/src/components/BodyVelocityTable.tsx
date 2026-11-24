import type { Diagnostics } from "../types";

const stages = [
  ["requested", "Requested command"],
  ["limited", "After applicable speed limits"],
  ["measured", "Simulated measurement"],
] as const;

export function BodyVelocityTable({
  motion,
}: {
  motion?: Diagnostics["motion"];
}) {
  return (
    <div className="diagnostic-table-wrap body-velocity-table">
      <table className="diagnostic-table" aria-label="Body velocity">
        <thead>
          <tr>
            <th scope="col">Motion stage</th>
            <th scope="col">Linear (m/s)</th>
            <th scope="col">Angular (rad/s)</th>
          </tr>
        </thead>
        <tbody>
          {stages.map(([stage, label]) => (
            <tr key={stage}>
              <th scope="row">{label}</th>
              <td>{motion?.[stage].linear.toFixed(4) ?? "—"}</td>
              <td>{motion?.[stage].angular.toFixed(4) ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
