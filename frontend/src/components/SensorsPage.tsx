import { Radio, ShieldCheck } from "lucide-react";
import type { SensorBundle, SensorConnection } from "../sensors";
import { scanAge, scanState } from "../sensors";
import { formatTimestamp } from "../utils/telemetry";
import { LidarVisualization } from "./sensors/LidarVisualization";
import { CameraMonitor } from "./sensors/CameraMonitor";
export function SensorsPage({
  bundle,
  connection,
  error,
  now,
}: {
  bundle: SensorBundle | null;
  connection: SensorConnection;
  error: string;
  now: number;
}) {
  const frame = bundle?.lidar ?? null;
  const state = scanState(frame, connection, now);
  const age = scanAge(frame, now);
  const ready = state === "READY";
  return (
    <div className="sensor-center">
      <div className="sensor-center-intro">
        <div>
          <span className="eyebrow">SENSOR CENTER / VIRTUAL PERCEPTION</span>
          <p>
            Read-only sensor visualization. Navigation and collision protection
            use the occupancy grid directly.
          </p>
        </div>
        <span className="tag">SIMULATION ONLY</span>
      </div>
      {(error || frame?.error) && (
        <div role="alert" className="connection-alert">
          {error || frame?.error}
        </div>
      )}
      <div className="sensor-center-grid">
        <section className="panel lidar-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">DETERMINISTIC GRID RAYCASTING</span>
              <h2>
                <Radio size={18} />
                2D LiDAR Visualization
              </h2>
            </div>
            <span className="sensor-source simulated">SIMULATED</span>
          </div>
          <div className="sensor-status-row">
            <span>
              Status{" "}
              <strong
                data-testid="lidar-status"
                className={ready ? "sensor-ready" : "sensor-warning"}
              >
                {state}
              </strong>
            </span>
            <span>
              Scan age{" "}
              <strong>
                {age === null ? "Unavailable" : `${(age / 1000).toFixed(2)} s`}
              </strong>
            </span>
            <span>
              Minimum hit{" "}
              <strong data-testid="lidar-min-distance">
                {ready && frame?.metadata.min_obstacle_distance != null
                  ? `${frame.metadata.min_obstacle_distance.toFixed(2)} m`
                  : "Unavailable"}
              </strong>
            </span>
          </div>
          <LidarVisualization frame={frame} ready={ready} />
          <div className="lidar-metrics">
            <span>
              Field of view
              <strong>
                {frame
                  ? (
                      ((frame.metadata.angle_max - frame.metadata.angle_min) *
                        180) /
                      Math.PI
                    ).toFixed(0)
                  : 180}
                °
              </strong>
            </span>
            <span>
              Beams<strong>{frame?.metadata.beam_count ?? 181}</strong>
            </span>
            <span>
              Maximum range<strong>{frame?.metadata.range_max ?? 5} m</strong>
            </span>
            <span>
              Virtual rate target
              <strong>{frame?.metadata.nominal_hz ?? 5} Hz</strong>
            </span>
          </div>
          <dl className="sensor-details">
            <div>
              <dt>Latest scan</dt>
              <dd>
                {frame?.timestamp
                  ? formatTimestamp(frame.timestamp)
                  : "Waiting for first scan"}
              </dd>
            </div>
            <div>
              <dt>Frame / sequence</dt>
              <dd>
                {frame
                  ? `${frame.frame_id} / ${frame.sequence}`
                  : "Unavailable"}
              </dd>
            </div>
            <div>
              <dt>Map / data source</dt>
              <dd>{frame?.metadata.map_frame ?? "map"} / SIMULATED</dd>
            </div>
            <div>
              <dt>Freshness</dt>
              <dd>
                {ready
                  ? "Fresh virtual scan"
                  : state === "STALE"
                    ? "Stale · points hidden"
                    : state === "DISCONNECTED"
                      ? "Disconnected · points hidden"
                      : "Waiting or unavailable · points hidden"}
              </dd>
            </div>
          </dl>
          <div className="sensor-interface">
            <span className="eyebrow">FUTURE ROS 2 CONTRACT / DISABLED</span>
            <p>/scan · sensor_msgs/LaserScan · meters and radians</p>
            <p>
              Virtual defaults only. These are not specifications of your
              physical LiDAR.
            </p>
          </div>
        </section>
        <CameraMonitor frame={bundle?.camera ?? null} />
      </div>
      <div className="sensor-center-note">
        <ShieldCheck size={18} />
        <p>
          All laser returns are synthetic map intersections. The camera test
          pattern contains no detections or measurements. Sensor streams cannot
          command motion; ROS 2, UART, GPIO and camera devices remain disabled.
        </p>
      </div>
    </div>
  );
}
