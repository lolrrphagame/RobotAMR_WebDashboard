import type { Telemetry } from "../types";
export function MissionSummary({ data }: { data: Telemetry | null }) {
  const pose = data?.pose,
    nav = data?.navigation;
  const operation = data?.operations.active;
  const status = operation?.status ?? nav?.status;
  const progress = operation?.progress ?? nav?.progress;
  return (
    <section
      className="panel pose-strip"
      aria-label="Authoritative robot pose and mission"
    >
      <div>
        <span>POSITION / MAP</span>
        <strong data-testid="robot-position">
          {pose ? `${pose.x.toFixed(2)}, ${pose.y.toFixed(2)} m` : "—"}
        </strong>
      </div>
      <div>
        <span>HEADING / CCW</span>
        <strong>
          {pose ? `${((pose.yaw * 180) / Math.PI).toFixed(1)}°` : "—"}
        </strong>
      </div>
      <div>
        <span>CONTROL AUTHORITY</span>
        <strong data-testid="control-authority">{data?.mode ?? "OFFLINE"}</strong>
      </div>
      <div>
        <span>MISSION / {operation ? "OPERATIONS" : (nav?.current_waypoint ?? "NO DESTINATION")}</span>
        <strong
          data-testid="mission-status"
          className={`mission-state ${status ?? ""}`}
        >
          {status ?? "OFFLINE"}
          {progress === undefined ? "" : ` · ${progress.toFixed(0)}%`}
        </strong>
      </div>
    </section>
  );
}
