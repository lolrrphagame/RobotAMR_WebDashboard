import { BodyVelocityTable } from "../BodyVelocityTable";
import { RpmChart } from "../RpmChart";
import type { Sample, Telemetry } from "../../types";
export function MotorDiagnostics({
  data,
  history,
}: {
  data: Telemetry | null;
  history: Sample[];
}) {
  const diag = data?.diagnostics;
  return (
    <>
      <div className="diagnostics-notice">
        SIMULATED MEASUREMENTS · Acceleration-limited wheel dynamics.
      </div>
      <div className="motor-diagnostics-grid">
        {["Left", "Right"].map((name, i) => {
          const motor = data?.motors[i];
          return (
            <section className="panel motor-diagnostic" key={name}>
              <div className="panel-heading">
                <h2>
                  {name} motor / M{i + 1}
                </h2>
                <span className="tag">SIMULATED</span>
              </div>
              <div className="motor-rpm">
                <div>
                  <span>Actual RPM</span>
                  <strong>{motor?.actual_rpm.toFixed(2) ?? "—"}</strong>
                </div>
                <div>
                  <span>Target RPM</span>
                  <strong>{motor?.target_rpm.toFixed(2) ?? "—"}</strong>
                </div>
              </div>
              <dl className="diagnostic-values">
                <div>
                  <dt>Tracking error (target − actual)</dt>
                  <dd data-testid={`rpm-error-${i}`}>
                    {motor ? `${motor.tracking_error_rpm.toFixed(2)} RPM` : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Normalized encoder</dt>
                  <dd>{motor?.encoder_count.toLocaleString() ?? "—"}</dd>
                </div>
                <div>
                  <dt>Raw encoder</dt>
                  <dd>{motor?.raw_encoder_count.toLocaleString() ?? "—"}</dd>
                </div>
                <div>
                  <dt>Wheel velocity</dt>
                  <dd>
                    {motor ? `${motor.wheel_velocity.toFixed(4)} m/s` : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Estimated net wheel travel</dt>
                  <dd>
                    {motor ? `${motor.travel_distance.toFixed(3)} m` : "—"}
                  </dd>
                </div>
              </dl>
            </section>
          );
        })}
      </div>
      <section className="panel motion-diagnostics">
        <div className="panel-heading">
          <h2>Commanded versus measured motion</h2>
          <span className="tag">SIMULATION</span>
        </div>
        <BodyVelocityTable motion={diag?.motion} />
        <div className="diagnostic-state-row">
          <span>
            Control authority <strong>{data?.mode ?? "—"}</strong>
          </span>
          <span>
            Motion limiting{" "}
            <strong>
              {diag ? (diag.motion.limit_active ? "Active" : "Inactive") : "—"}
            </strong>
          </span>
          <span>
            Autonomous speed cap{" "}
            <strong>
              {diag
                ? diag.motion.autonomous_limit_active ? "Active" : "Inactive"
                : "—"}
            </strong>
          </span>
          <span>
            RPM saturation{" "}
            <strong>
              {diag
                ? diag.saturation.active
                  ? "ACTIVE"
                  : "Not limiting"
                : "—"}
            </strong>
          </span>
          <span>
            Wheel limit <strong>{diag ? `${diag.saturation.limit_rpm} RPM` : "—"}</strong>
          </span>
          <span>
            Pose clearance{" "}
            <strong>
              {data
                ? data.clearance.pose_clear
                  ? "Clear"
                  : "OBSTRUCTED"
                : "—"}
            </strong>
          </span>
          <span>
            Watchdog <strong>{diag?.safety.watchdog ?? "—"}</strong>
          </span>
          <span>
            STOP latch{" "}
            <strong>
              {diag ? (diag.safety.stop_active ? "ACTIVE" : "Released") : "—"}
            </strong>
          </span>
        </div>
        <p className="diagnostic-footnote">
          Manual watchdog: 600 ms · Autonomous lease: 1.5 s · Latest STOP:{" "}
          {diag?.safety.last_stop_reason ?? "No STOP issued this session"}
        </p>
      </section>
      <div className="motor-diagnostics-grid">
        <RpmChart
          history={history}
          motor="left"
          windowLabel="Up to 60 seconds"
        />
        <RpmChart
          history={history}
          motor="right"
          windowLabel="Up to 60 seconds"
        />
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Future PI telemetry contract</h2>
          <span className="tag">UNAVAILABLE</span>
        </div>
        <p className="diagnostic-footnote">
          No PI gains, PWM output, firmware control error or integral
          measurements are supplied by this simulator.
        </p>
        <div className="diagnostic-table-wrap">
          <table className="diagnostic-table">
            <thead>
              <tr>
                <th>Motor</th>
                <th>Kp</th>
                <th>Ki</th>
                <th>PWM</th>
                <th>Firmware control error</th>
                <th>Integral term</th>
              </tr>
            </thead>
            <tbody>
              {["Left", "Right"].map((name, motorIndex) => (
                <tr key={name}>
                  <td>{name}</td>
                  {(['kp','ki','pwm','control_error','integral_term'] as const).map(key => (
                    <td key={key} className={data?.motors[motorIndex].pi[key] == null ? 'unavailable' : ''}>
                      {data?.motors[motorIndex].pi[key] ?? 'Unavailable'}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel" aria-labelledby="integration-status-title">
        <div className="panel-heading"><h2 id="integration-status-title">Integration status</h2></div>
        <dl className="diagnostic-values integration-status">
          <div><dt>Current backend</dt><dd>{diag?.integration_status.backend === "simulation" ? "Simulation" : "—"}</dd></div>
          {([
            ["ROS 2", "ros2_connected"],
            ["Nav2", "nav2_connected"],
            ["ESP32-S3 hardware telemetry", "esp32_s3_connected"],
          ] as const).map(([label, key]) => (
            <div key={key}><dt>{label}</dt><dd>{diag ? (diag.integration_status[key] ? "Connected" : "Not connected") : "—"}</dd></div>
          ))}
        </dl>
      </section>
    </>
  );
}
