import {
  Activity,
  Battery,
  Bot,
  ChevronRight,
  CircleHelp,
  CircuitBoard,
  Compass,
  Cpu,
  Gauge,
  LayoutDashboard,
  Radio,
  Settings,
  ShieldCheck,
  Terminal,
  Thermometer,
  Timer,
  Unplug,
  Wifi,
  Zap,
} from "lucide-react";
import { useState } from "react";
import { NavigationPage } from "./components/NavigationPage";
import { MissionSummary } from "./components/MissionSummary";
import { ManualControl } from "./components/ManualControl";
import { RpmChart } from "./components/RpmChart";
import { useRobot } from "./hooks/useRobot";
const pages = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Manual Control", icon: Compass },
  { name: "Navigation", icon: Radio },
  { name: "Diagnostics", icon: Activity },
  { name: "Settings", icon: Settings },
];
function App() {
  const [page, setPage] = useState("Overview");
  const { data, history, connection, error, send, stop, release } = useRobot();
  const connected = connection === "connected";
  const live = connected ? data : null;
  const value = (n: number | undefined, decimals = 2) =>
    n === undefined ? "—" : n.toFixed(decimals);
  const health = live?.health;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" onClick={(e) => e.preventDefault()}>
          <span className="brand-symbol">
            <Bot size={27} />
          </span>
          <span>
            PBL4<span className="brand-sub">ROBOTICS LAB</span>
          </span>
        </a>
        <div className="workspace-label">
          WORKSPACE <span>PHASE 02</span>
        </div>
        <nav aria-label="Main navigation">
          {pages.map(({ name, icon: Icon }) => (
            <button
              key={name}
              className={page === name ? "nav-item selected" : "nav-item"}
              onClick={() => {
                release();
                setPage(name);
              }}
            >
              <Icon size={19} />
              {name}
              {name === page && <span className="nav-mark" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="simulation-card">
            <ShieldCheck size={21} />
            <strong>Safe simulation</strong>
            <p>
              Virtual robot environment.
              <br />
              Hardware is never connected.
            </p>
            <span className="tag">SIMULATION ONLY</span>
          </div>
          <div className="lab-footer">
            <span className="avatar">PL</span>
            <div>
              PBL4 Engineering<small>AMR development platform</small>
            </div>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />
            <strong>{page}</strong>
          </div>
          <div className="flex items-center gap-4">
            <span className="simulation-pill">
              <ShieldCheck size={14} /> SIMULATION
            </span>
            <span className={`connection ${connected ? "" : "offline"}`}>
              <span className="status-dot" />
              {connected
                ? "Stream connected"
                : connection === "connecting"
                  ? "Connecting…"
                  : "Disconnected"}
            </span>
          </div>
        </header>
        <div className="page-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">AMR OPERATIONS / PBL4</div>
              <h1>{page === "Overview" ? "Mission overview" : page}</h1>
              <p>Real-time insight into your autonomous mobile robot.</p>
            </div>
            <div className="robot-badge">
              <Bot size={24} />
              <div>
                AMR–01<small>Differential drive · Virtual robot</small>
              </div>
            </div>
          </div>
          <div className="simulation-banner">
            <ShieldCheck size={18} />
            <span>
              <strong>Simulation environment active.</strong> All telemetry and
              controls are simulated. ROS 2, UART and GPIO are disabled.
            </span>
            <span className="banner-phase">PHASE 2</span>
          </div>
          {(!connected || error) && (
            <div className="connection-alert" role="status">
              <Unplug size={19} />
              <span>
                {error ||
                  (connection === "connecting"
                    ? "Waiting for the simulation service…"
                    : "Connection lost. Commands cleared; retrying every 2 seconds.")}{" "}
                {data && !connected
                  ? "Last telemetry is stale and hidden."
                  : ""}
              </span>
            </div>
          )}
          {(page === "Overview" || page === "Manual Control") && (
            <>
              <MissionSummary data={live} />
              {live?.mode === "AUTONOMOUS" && (
                <div className="simulation-banner">
                  Autonomous mode owns motion. Cancel the mission on Navigation
                  or press STOP before manual driving.{" "}
                  <button className="navigation-stop" onClick={stop}>
                    STOP
                  </button>
                </div>
              )}
              <div className="telemetry-grid">
                <article className="metric panel">
                  <div className="metric-label">
                    Robot status <Wifi size={19} />
                  </div>
                  <div className="metric-value status-value">
                    {connected ? (
                      <>
                        <span className="status-dot" />
                        Online
                      </>
                    ) : (
                      "Offline"
                    )}
                  </div>
                  <div className="metric-footer">
                    <span data-testid="operating-mode">
                      {live?.mode ?? "AWAITING CONNECTION"}
                    </span>
                    <span>SIMULATED</span>
                  </div>
                </article>
                <article className="metric panel">
                  <div className="metric-label">
                    Linear velocity <Gauge size={19} />
                  </div>
                  <div className="metric-value">
                    {value(live?.linear_velocity)}
                    <small>m/s</small>
                  </div>
                  <div className="metric-footer">
                    Longitudinal motion<span className="cyan">v</span>
                  </div>
                </article>
                <article className="metric panel">
                  <div className="metric-label">
                    Angular velocity <Compass size={19} />
                  </div>
                  <div className="metric-value">
                    {value(live?.angular_velocity)}
                    <small>rad/s</small>
                  </div>
                  <div className="metric-footer">
                    Rotational motion<span className="purple">ω</span>
                  </div>
                </article>
                <article className="metric panel">
                  <div className="metric-label">
                    Wheel speed <CircuitBoard size={19} />
                  </div>
                  <div className="wheel-values">
                    <div>
                      <small>LEFT</small>
                      {value(live?.motors[0].actual_rpm, 1)}
                      <em>RPM</em>
                    </div>
                    <div>
                      <small>RIGHT</small>
                      {value(live?.motors[1].actual_rpm, 1)}
                      <em>RPM</em>
                    </div>
                  </div>
                  <div className="metric-footer">
                    Wheel response model<span>2 MOTORS</span>
                  </div>
                </article>
              </div>
              <div className="operations-grid">
                <div className="chart-stack">
                  <RpmChart history={connected ? history : []} motor="left" />
                  <RpmChart history={connected ? history : []} motor="right" />
                </div>
                <ManualControl
                  connected={connected && live?.mode !== "AUTONOMOUS"}
                  send={send}
                  stop={stop}
                  release={release}
                />
              </div>
            </>
          )}
          {(page === "Overview" || page === "Diagnostics") && (
            <div className="bottom-grid">
              <section className="panel">
                <div className="panel-heading">
                  <h2>
                    <Cpu size={18} />
                    System health
                  </h2>
                  <span className="tag">SIMULATED</span>
                </div>
                <div className="health-list">
                  {[
                    {
                      label: "CPU load",
                      Icon: Cpu,
                      number: health?.cpu_percent,
                      suffix: "%",
                      max: 100,
                    },
                    {
                      label: "Memory",
                      Icon: CircuitBoard,
                      number: health?.memory_percent,
                      suffix: "%",
                      max: 100,
                    },
                    {
                      label: "CPU temperature",
                      Icon: Thermometer,
                      number: health?.temperature_c,
                      suffix: "°C",
                      max: 85,
                    },
                    {
                      label: "Battery",
                      Icon: Battery,
                      number: health?.battery_percent,
                      suffix: "%",
                      max: 100,
                    },
                  ].map(({ label, Icon, number, suffix, max }) => (
                    <div key={label} className="health-row">
                      <div>
                        <span>
                          <Icon size={16} />
                          {label}
                        </span>
                        <strong>
                          {value(number, 0)}
                          {number === undefined ? "" : suffix}
                        </strong>
                      </div>
                      <div className="progress-track">
                        <span
                          style={{ width: `${((number ?? 0) / max) * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </section>
              <section className="panel encoder-panel">
                <div className="panel-heading">
                  <h2>
                    <Zap size={18} />
                    Encoder feedback
                  </h2>
                </div>
                {["Left wheel", "Right wheel"].map((name, index) => (
                  <div className="encoder-row" key={name}>
                    <span>
                      {name}
                      <small>
                        {index === 0 ? "M1 / CHANNEL A+B" : "M2 / CHANNEL A+B"}
                      </small>
                    </span>
                    <strong>
                      {live
                        ? live.motors[index].encoder_count.toLocaleString()
                        : "—"}
                      <small>counts</small>
                    </strong>
                  </div>
                ))}
                <div className="encoder-note">
                  ≈ 3,960 counts / revolution
                  <br />
                  Signed quadrature count · simulated
                </div>
              </section>
              <section className="panel events-panel">
                <div className="panel-heading">
                  <h2>
                    <Terminal size={18} />
                    Event stream
                  </h2>
                  <span className="tag">{live?.events.length ?? 0} EVENTS</span>
                </div>
                <div className="events" aria-label="Robot event logs">
                  {!live && <p className="muted">Waiting for live events…</p>}
                  {live?.events.map((event) => (
                    <div className="event" key={event.id}>
                      <span className={`event-dot ${event.level}`} />
                      <div>
                        <p>{event.message}</p>
                        <time>
                          {new Date(event.time).toLocaleTimeString()} ·{" "}
                          {event.level.toUpperCase()}
                        </time>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}
          {page === "Diagnostics" && (
            <section className="panel details-panel">
              <h2>Simulation interfaces</h2>
              <div className="detail-grid">
                <div>
                  WebSocket transport<strong>{connection}</strong>
                </div>
                <div>
                  Mock battery voltage
                  <strong>{value(health?.battery_voltage, 1)} V</strong>
                </div>
                <div>
                  ROS 2 Humble<strong>Not connected</strong>
                </div>
                <div>
                  UART / GPIO<strong>Disabled</strong>
                </div>
                <div>
                  Current pose clearance
                  <strong>
                    {live
                      ? live.clearance.pose_clear
                        ? "Clear"
                        : "OBSTRUCTED"
                      : "—"}
                  </strong>
                </div>
              </div>
            </section>
          )}
          {page === "Navigation" && (
            <NavigationPage
              data={live}
              connected={connected}
              send={send}
              stop={stop}
            />
          )}
          {page === "Settings" && (
            <section className="panel details-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">READ-ONLY CONFIGURATION</span>
                  <h2>Robot & simulation parameters</h2>
                </div>
                <ShieldCheck size={24} />
              </div>
              <div className="detail-grid">
                {[
                  ["Wheel radius", "0.0435 m"],
                  ["Wheel speed limit", "40 RPM per wheel"],
                  ["Chassis", "250 × 250 mm · two wheels + caster"],
                  [
                    "Encoder polarity (raw)",
                    live?.drive.encoder_polarity.join(", ") ?? "+1, -1",
                  ],
                  ["Autonomous heartbeat timeout", "1.5 s"],
                  ["Wheel separation", "0.300 m"],
                  ["Encoder resolution", "≈ 3,960 counts/rev"],
                  ["Telemetry rate", "10 Hz"],
                  ["Command timeout", "600 ms"],
                  ["Control heartbeat", "150 ms"],
                  ["Planned UART baud", "57,600 (disabled)"],
                  ["Planned compute", "Raspberry Pi 4"],
                  ["Planned motor controller", "ESP32-S3 N16R8"],
                  ["Operating environment", "Simulation only"],
                ].map(([label, val]) => (
                  <div key={label}>
                    {label}
                    <strong>{val}</strong>
                  </div>
                ))}
              </div>
              <p className="muted">
                Configuration is fixed for Phase 2. No hardware adapters are
                installed or invoked.
              </p>
            </section>
          )}
          <footer className="page-footer">
            <span>
              <ShieldCheck size={14} /> PBL4 AMR · Simulation sandbox
            </span>
            <span>
              <Timer size={14} /> Uptime{" "}
              {live
                ? `${Math.floor(live.uptime / 60)}m ${live.uptime % 60}s`
                : "—"}
              <span className="footer-divider">|</span>
              <CircleHelp size={14} /> Phase 2 · v2.0
            </span>
          </footer>
        </div>
      </main>
    </div>
  );
}
export default App;
