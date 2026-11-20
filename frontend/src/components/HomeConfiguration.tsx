import { Home } from "lucide-react";
import type { Command, Goal, Telemetry } from "../types";
export function HomeConfiguration({
  data,
  selected,
  send,
}: {
  data: Telemetry | null;
  selected?: Goal | null;
  send: (command: Command) => void;
}) {
  const locked =
    !data ||
    !!data.operations.active ||
    ["running", "paused"].includes(data.navigation.status);
  const home = data?.home;
  return (
    <section className="panel home-configuration">
      <div className="panel-heading">
        <h2>
          <Home size={18} />
          Saved Home
        </h2>
        <span className="tag">
          {data?.configuration.storage === "local-file"
            ? "PERSISTENT"
            : "SIMULATION"}
        </span>
      </div>
      <div className="nav-body">
        <div className="saved-home" data-testid="saved-home">
          {home
            ? `${home.x.toFixed(2)}, ${home.y.toFixed(2)} m · ${((home.yaw * 180) / Math.PI).toFixed(1)}°`
            : "Waiting for configuration…"}
        </div>
        <p className="muted">
          Saving Home changes a destination, never the current robot pose.
        </p>
        <div className="home-actions">
          {selected && (
            <button
              disabled={locked}
              onClick={() =>
                send({
                  type: "configuration",
                  action: "set_home",
                  goal: selected,
                })
              }
            >
              Set Selected as Home
            </button>
          )}
          <button
            disabled={locked}
            onClick={() =>
              send({ type: "configuration", action: "current_home" })
            }
          >
            Set Current Pose as Home
          </button>
          <button
            disabled={locked}
            onClick={() =>
              send({ type: "configuration", action: "reset_home" })
            }
          >
            Reset Default Home
          </button>
        </div>
        {locked && data && (
          <p className="home-locked">
            Cancel the running or paused mission before changing Home.
          </p>
        )}
        {data?.configuration.load_warnings.map((warning, index) => (
          <p className="home-locked" key={index}>
            {warning}
          </p>
        ))}
      </div>
    </section>
  );
}
