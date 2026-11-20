import type { Telemetry } from "../types";
export function MissionSummary({ data }: { data: Telemetry | null }) {
  const pose = data?.pose,
    nav = data?.navigation;
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
        <span>OPERATING MODE</span>
        <strong>{data?.mode ?? "OFFLINE"}</strong>
      </div>
      <div>
        <span>MISSION / {nav?.current_waypoint ?? "NO DESTINATION"}</span>
        <strong
          data-testid="mission-status"
          className={`mission-state ${nav?.status}`}
        >
          {nav?.status ?? "OFFLINE"}
          {nav ? ` · ${nav.progress.toFixed(0)}%` : ""}
        </strong>
      </div>
    </section>
  );
}
