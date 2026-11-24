import { Suspense, lazy, useState, useEffect } from "react";
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
  Radar,
  Settings,
  ShieldCheck,
  Terminal,
  Thermometer,
  Timer,
  Unplug,
  Wifi,
  Zap,
} from "lucide-react";
const MissionsPage = lazy(() =>
  import("./components/MissionsPage").then((m) => ({
    default: m.MissionsPage,
  })),
);
import { OperatorSession } from "./components/OperatorSession";
import { AuthBoundary } from "./components/AuthBoundary";
import { ThemeSelector, ThemePreferences } from "./theme/ThemeSelector";

const DiagnosticsPage = lazy(() =>
  import("./components/DiagnosticsPage").then((m) => ({
    default: m.DiagnosticsPage,
  })),
);
import { HomeConfiguration } from "./components/HomeConfiguration";
import { formatTimestamp } from "./utils/telemetry";
const NavigationPage = lazy(() =>
  import("./components/NavigationPage").then((m) => ({
    default: m.NavigationPage,
  })),
);
import { MissionSummary } from "./components/MissionSummary";
import { ManualControl } from "./components/ManualControl";
import { MotionSettings } from "./components/MotionSettings";
const RpmChart = lazy(() =>
  import("./components/RpmChart").then((m) => ({ default: m.RpmChart })),
);
import { useSensors } from "./hooks/useSensors";
const SensorsPage = lazy(() =>
  import("./components/SensorsPage").then((m) => ({ default: m.SensorsPage })),
);
import { useRobot } from "./hooks/useRobot";
const pages = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Manual Control", icon: Compass },
  { name: "Navigation", icon: Radio },
  { name: "Missions", icon: Compass },
  { name: "Sensors", icon: Radar },
  { name: "Diagnostics", icon: Activity },
  { name: "Settings", icon: Settings },
];
const pagePath = (name: string) =>
  "/" + name.toLowerCase().replaceAll(" ", "-");
const pageFromPath = () =>
  pages.find((p) => pagePath(p.name) === location.pathname)?.name ?? "Overview";
function Dashboard() {
  const [page, setPage] = useState(pageFromPath);
  useEffect(() => {
    const navigate = () => setPage(pageFromPath());
    window.addEventListener("popstate", navigate);
    return () => window.removeEventListener("popstate", navigate);
  }, []);
  const {
    operator,
    data,
    history,
    connection,
    error,
    historyError,
    send,
    stop,
    release,
  } = useRobot();
  const sensors = useSensors(page === "Sensors" || page === "Navigation");
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
          WORKSPACE <span>PHASE 5E.2</span>
        </div>
        <nav aria-label="Main navigation">
          {pages.map(({ name, icon: Icon }) => (
            <button
              key={name}
              className={page === name ? "nav-item selected" : "nav-item"}
              onClick={() => {
                release();
                if (location.pathname !== pagePath(name))
                  window.history.pushState(null, "", pagePath(name));
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
          <div className="topbar-tools">
            <ThemeSelector />
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
            <span className="banner-phase">PHASE 5E.2</span>
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
          <OperatorSession operator={operator} />
          <Suspense fallback={<p role="status">Loading view…</p>}>
            {(page === "Overview" || page === "Manual Control") && (
              <>
                <MissionSummary data={live} />
                {live?.mode === "AUTONOMOUS" && (
                  <div className="simulation-banner">
                    Manual driving is locked while an autonomous mission owns motion.
                    <button
                      className="navigation-stop"
                      disabled={!operator}
                      onClick={stop}
                    >
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
                      <span>Control authority</span>
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
                    <RpmChart
                      history={connected ? history.slice(-150) : []}
                      motor="left"
                    />
                    <RpmChart
                      history={connected ? history.slice(-150) : []}
                      motor="right"
                    />
                  </div>
                  <ManualControl
                    readOnly={!operator}
                    connected={connected}
                    authority={live?.mode}
                    wheelLimit={live?.drive.max_rpm}
                    send={send}
                    stop={stop}
                    release={release}
                  />
                </div>
              </>
            )}
            {page === "Overview" && (
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
                          {index === 0
                            ? "M1 / CHANNEL A+B"
                            : "M2 / CHANNEL A+B"}
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
                    {live ? `${live.drive.encoder_cpr.toLocaleString()} counts / revolution` : "Encoder resolution unavailable"}
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
                    <span className="tag">
                      {live?.events.length ?? 0} EVENTS
                    </span>
                  </div>
                  <div className="events" aria-label="Robot event logs">
                    {!live && <p className="muted">Waiting for live events…</p>}
                    {live?.events.map((event) => (
                      <div className="event" key={event.id}>
                        <span className={`event-dot ${event.level}`} />
                        <div>
                          <p>{event.message}</p>
                          <time>
                            {formatTimestamp(event.time)} ·{" "}
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
              <DiagnosticsPage
                data={live}
                history={history}
                lastTimestamp={data?.timestamp}
                historyError={historyError}
                events={data?.events ?? []}
              />
            )}
            {page === "Missions" && (
              <MissionsPage send={send} connected={connected && operator} />
            )}
            {page === "Sensors" && (
              <SensorsPage
                bundle={sensors.bundle}
                connection={sensors.connection}
                error={sensors.error}
                now={sensors.now}
              />
            )}
            {page === "Navigation" && (
              <NavigationPage
                lidar={
                  sensors.state === "READY" &&
                  sensors.bundle &&
                  sensors.bundle.session_id === live?.session_id
                    ? sensors.bundle.lidar
                    : null
                }
                data={live}
                connected={connected && operator}
                send={send}
                stop={stop}
              />
            )}
            {page === "Settings" && (
              <>
                <ThemePreferences />
                <MotionSettings data={live} operator={operator} />
                <HomeConfiguration
                  readOnly={!operator}
                  data={live}
                  send={send}
                />
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
                      [
                        "Encoder polarity (raw)",
                        live?.drive.encoder_polarity.join(", ") ?? "+1, -1",
                      ],
                      ["Autonomous heartbeat timeout", "1.5 s"],
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
                    Home and waypoints are saved on the backend. Drive geometry
                    remains read-only. No hardware adapters are installed or
                    invoked.
                  </p>
                </section>
              </>
            )}
          </Suspense>
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
              <CircleHelp size={14} /> Phase 5E.2
            </span>
          </footer>
        </div>
      </main>
    </div>
  );
}
export default function App() {
  return (
    <AuthBoundary>
      <Dashboard />
    </AuthBoundary>
  );
}
