import type { Telemetry } from "../../types";
import { formatTimestamp } from "../../utils/telemetry";
export function Communication({ data }: { data: Telemetry | null }) {
  const interfaces = data?.diagnostics.interfaces;
  return (
    <>
      <div className="diagnostics-notice">
        HARDWARE INTERFACES DISABLED · Planned contracts only. No ROS graph,
        serial port or sensor is opened.
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>ROS 2 Humble / planned interfaces</h2>
          <span className="tag">DISABLED</span>
        </div>
        <div className="diagnostic-state-row">
          <span>
            Connection <strong>Not connected</strong>
          </span>
          <span>
            Observed rate <strong>Unavailable</strong>
          </span>
          <span>
            Last message <strong>Unavailable</strong>
          </span>
        </div>
        <div className="diagnostic-table-wrap">
          <table className="diagnostic-table">
            <thead>
              <tr>
                <th>Planned node</th>
                <th>Planned topic</th>
                <th>Message contract</th>
                <th>Target rate</th>
              </tr>
            </thead>
            <tbody>
              {interfaces?.ros2.planned.map((row) => (
                <tr key={row.topic}>
                  <td>{row.node}</td>
                  <td>{row.topic}</td>
                  <td>{row.message_type}</td>
                  <td>{row.expected_hz} Hz (planned)</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="diagnostic-footnote">
          Rates are proposed design targets, not measured or confirmed hardware
          frequencies. Future diagnostics:{" "}
          {interfaces?.ros2.diagnostics_contract ??
            "diagnostic_msgs/DiagnosticArray on /diagnostics (planned)"}
          .
        </p>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>ESP32-S3 / UART monitor</h2>
          <span className="tag">DISABLED</span>
        </div>
        <div className="detail-grid">
          <div>
            Planned baud
            <strong>{interfaces?.uart.planned_baud ?? 57600}</strong>
          </div>
          <div>
            Connection<strong>Not connected</strong>
          </div>
          <div>
            Hardware heartbeat / watchdog<strong>Unavailable</strong>
          </div>
          <div>
            TX / RX bytes<strong>Unavailable / Unavailable</strong>
          </div>
          <div>
            Command / fault counters<strong>Unavailable / Unavailable</strong>
          </div>
          <div>
            Last UART message<strong>Unavailable</strong>
          </div>
        </div>
        <p className="diagnostic-footnote">
          WebSocket simulator commands are not UART traffic. Hardware counters
          remain unavailable until an adapter provides real data.
        </p>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Simulation service / actual in-process counters</h2>
          <span className="tag">SIMULATION</span>
        </div>
        <div className="detail-grid">
          {Object.entries(data?.diagnostics.counters ?? {}).map(
            ([name, value]) => (
              <div key={name}>
                {name.replaceAll("_", " ")}
                <strong>{value.toLocaleString()}</strong>
              </div>
            ),
          )}
        </div>
        <p className="diagnostic-footnote">
          Latest simulation snapshot:{" "}
          {data
            ? formatTimestamp(data.timestamp)
            : "Disconnected; no fresh sample"}
          . These counters reset on backend restart.
        </p>
      </section>
    </>
  );
}
