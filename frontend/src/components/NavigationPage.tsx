import type { LidarFrame } from "../sensors";
import { useEffect, useState } from "react";
import {
  Flag,
  Home,
  Pause,
  Play,
  Save,
  ShieldCheck,
  Square,
  Trash2,
} from "lucide-react";
import { HomeConfiguration } from "./HomeConfiguration";
import { BodyVelocityTable } from "./BodyVelocityTable";
import { formatTimestamp } from "../utils/telemetry";
import { NavigationMap } from "./NavigationMap";
import { MissionSummary } from "./MissionSummary";
import type {
  Command,
  Goal,
  OccupancyGrid,
  Telemetry,
  WaypointName,
} from "../types";

export function NavigationPage({
  data,
  connected,
  send,
  stop,
  lidar,
}: {
  data: Telemetry | null;
  connected: boolean;
  send: (command: Command) => void;
  stop: () => void;
  lidar: LidarFrame | null;
}) {
  const [showLidar, setShowLidar] = useState(false);
  const [grid, setGrid] = useState<OccupancyGrid | null>(null);
  const [mapError, setMapError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState<Goal | null>(null);
  const [sequence, setSequence] = useState<WaypointName[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    setMapError("");
    fetch("/api/map", { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok)
          throw Error(`Map request failed (${response.status})`);
        const next = (await response.json()) as OccupancyGrid;
        if (
          !Array.isArray(next.data) ||
          next.data.length !== next.width * next.height
        )
          throw Error("Invalid occupancy grid");
        setGrid(next);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setMapError(String(error));
      });
    return () => controller.abort();
  }, [attempt]);
  const nav = data?.navigation;
  const operation = data?.operations.active;
  const missionStatus = operation?.status ?? nav?.status;
  const missionProgress = operation?.progress ?? nav?.progress ?? 0;
  const waiting = operation?.steps[operation.current_step]?.kind === "wait";
  const active = missionStatus === "running" || missionStatus === "paused";
  const canPlan =
    connected && !active && data?.mode !== "MANUAL";
  const limits = data?.configuration.autonomous_speed_limits;
  const diagnostics = data?.diagnostics;
  const activeLimits = [
    diagnostics?.motion.autonomous_limit_active && "autonomous speed caps",
    diagnostics?.saturation.active && "wheel RPM saturation",
  ].filter(Boolean).join(" and ");
  const goal = selected ?? { x: 2, y: 1, yaw: 0, name: "Destination" };
  const names: WaypointName[] = ["A", "B", "C"];
  return (
    <>
      <MissionSummary data={data} />
      {data?.mode === "AUTONOMOUS" && (
        <div className="navigation-authority" role="status">
          <strong>{missionStatus === "paused" ? "Autonomous paused — Simulation controller" : "Autonomous active — Simulation controller"}</strong>
          {operation && <span>Mission Operations reservation{waiting ? " · WAIT step" : ""}</span>}
        </div>
      )}
      <div className="navigation-sensor-toggle">
        <label>
          <input
            type="checkbox"
            checked={showLidar}
            onChange={(e) => setShowLidar(e.target.checked)}
          />
          Show simulated LiDAR
        </label>
        <span>
          {showLidar
            ? lidar
              ? "SIMULATED · acquisition pose · visualization only"
              : "No fresh simulated scan; overlay hidden."
            : "Optional visualization; planner and collision guard remain independent."}
        </span>
      </div>
      <div className="navigation-layout">
        <div className="navigation-main">
          {grid ? (
            <NavigationMap
              lidar={showLidar ? lidar : null}
              grid={grid}
              data={data}
              selected={selected}
              onSelect={setSelected}
              disabled={!connected}
            />
          ) : (
            <section className="panel map-loading" role="status">
              {mapError || "Loading simulated occupancy grid…"}
              {mapError && (
                <button
                  className="secondary-button"
                  onClick={() => setAttempt((n) => n + 1)}
                >
                  Retry map
                </button>
              )}
            </section>
          )}
          <section className="panel navigation-motion" aria-labelledby="navigation-motion-title">
            <div className="panel-heading"><h2 id="navigation-motion-title">Navigation motion</h2></div>
            <div className="diagnostic-state-row">
              <span>Configured autonomous caps <strong>{limits ? `${limits.max_linear} m/s · ${limits.max_angular} rad/s` : "—"}</strong></span>
              <span>Effective wheel speed limit <strong>{data ? `${data.drive.max_rpm} RPM` : "—"}</strong></span>
              <span>Active limiting <strong>{diagnostics ? (activeLimits || "Inactive") : "—"}</strong></span>
            </div>
            <BodyVelocityTable motion={diagnostics?.motion} />
          </section>
          <section className="panel nav-events">
            <div className="panel-heading">
              <h2>Mission event stream</h2>
              <span className="tag">SIMULATION</span>
            </div>
            <div className="events">
              {data?.events.slice(0, 5).map((event) => (
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
              {!data && <p className="muted">Waiting for live events…</p>}
            </div>
          </section>
        </div>
        <div className="navigation-side">
          <section className="panel nav-controls">
            <div className="panel-heading">
              <h2>
                <Flag size={18} />
                Destination & mission
              </h2>
              <span className="tag">SIM</span>
            </div>
            <div className="nav-body">
              <div className="goal-coordinates">
                <label htmlFor="goal-x">
                  X position (m)
                  <input
                    id="goal-x"
                    type="number"
                    min="0"
                    max="8"
                    step="0.1"
                    value={goal.x}
                    disabled={!connected}
                    onChange={(e) =>
                      setSelected({ ...goal, x: Number(e.target.value) })
                    }
                  />
                </label>
                <label htmlFor="goal-y">
                  Y position (m)
                  <input
                    id="goal-y"
                    type="number"
                    min="0"
                    max="6"
                    step="0.1"
                    value={goal.y}
                    disabled={!connected}
                    onChange={(e) =>
                      setSelected({ ...goal, y: Number(e.target.value) })
                    }
                  />
                </label>
              </div>
              <label className="heading-label" htmlFor="goal-heading">
                Target heading{" "}
                <strong>{((goal.yaw * 180) / Math.PI).toFixed(0)}°</strong>
              </label>
              <input
                id="goal-heading"
                aria-label="Target heading"
                type="range"
                min="-180"
                max="180"
                step="5"
                value={(goal.yaw * 180) / Math.PI}
                disabled={!connected}
                onChange={(e) =>
                  setSelected({
                    ...goal,
                    yaw: (Number(e.target.value) * Math.PI) / 180,
                  })
                }
              />
              <div className="nav-heading-ticks">
                <span>−180°</span>
                <span>+x = 0° · CCW positive</span>
                <span>180°</span>
              </div>
              <div className="nav-action-grid">
                <button
                  disabled={!canPlan || !grid}
                  onClick={() =>
                    send({ type: "navigation", action: "plan", goal })
                  }
                >
                  <Flag size={15} />
                  Plan path
                </button>
                <button
                  className="primary-action"
                  disabled={!canPlan || !grid}
                  onClick={() =>
                    send({ type: "navigation", action: "start", goal })
                  }
                >
                  <Play size={15} />
                  Start navigation
                </button>
                <button
                  disabled={!connected || missionStatus !== "running"}
                  onClick={() => send({ type: "navigation", action: "pause" })}
                >
                  <Pause size={15} />
                  Pause
                </button>
                <button
                  disabled={!connected || missionStatus !== "paused"}
                  onClick={() => send({ type: "navigation", action: "resume" })}
                >
                  <Play size={15} />
                  Resume
                </button>
                <button
                  disabled={
                    !connected ||
                    !["running", "paused", "ready", "blocked"].includes(
                      missionStatus ?? "",
                    )
                  }
                  onClick={() => send({ type: "navigation", action: "cancel" })}
                >
                  <Square size={15} />
                  Cancel mission
                </button>
                <button
                  disabled={!canPlan}
                  onClick={() => send({ type: "navigation", action: "home" })}
                >
                  <Home size={15} />
                  Return home
                </button>
              </div>
              <button
                className="navigation-stop"
                onClick={stop}
                disabled={!connected}
              >
                <Square size={17} fill="currentColor" />
                STOP · CANCEL ALL MOTION
              </button>
              {connected && data?.mode === "MANUAL" && (
                <p className="muted">
                  Manual control owns motion. Release manual input to start
                  navigation.
                </p>
              )}
              <div className="mission-details">
                <div>
                  <span>Mission state</span>
                  <strong data-testid="navigation-status">
                    {missionStatus ?? "offline"}
                  </strong>
                </div>
                <div>
                  <span>Active destination</span>
                  <strong>
                    {nav?.destination
                      ? `${nav.destination.name ?? "Goal"} · ${nav.destination.x.toFixed(2)}, ${nav.destination.y.toFixed(2)} m`
                      : "None"}
                  </strong>
                </div>
                <div>
                  <span>Waypoint</span>
                  <strong>
                    {nav?.waypoint_count
                      ? `${nav.waypoint_index} / ${nav.waypoint_count}`
                      : "—"}
                  </strong>
                </div>
              </div>
              <div className="nav-progress">
                <div>
                  <span>Mission progress</span>
                  <strong>{missionProgress.toFixed(0)}%</strong>
                </div>
                <progress
                  max="100"
                  value={missionProgress}
                  aria-label="Mission progress"
                />
              </div>
              <p className="mission-reason" role="status">
                {operation ? (operation.reason ?? operation.name) : (nav?.reason ?? "Connect to the simulation service to begin.")}
              </p>
            </div>
          </section>
          <HomeConfiguration
            data={data}
            selected={goal}
            readOnly={!connected}
            send={send}
          />
          <section className="panel waypoint-panel">
            <div className="panel-heading">
              <h2>
                <Save size={17} />
                Waypoints
              </h2>
              <span className="tag">A / B / C</span>
            </div>
            <div className="nav-body">
              <p className="muted">
                Save the selected goal, or use the robot’s current pose.
              </p>
              <button
                className="use-pose"
                disabled={!data}
                onClick={() =>
                  data && setSelected({ ...data.pose, name: "Destination" })
                }
              >
                Use current robot pose
              </button>
              <div className="waypoint-list">
                {names.map((name) => {
                  const point = nav?.waypoints[name];
                  return (
                    <div className="waypoint-row" key={name}>
                      <div className="waypoint-info">
                        <span className="waypoint-letter">{name}</span>
                        <span>
                          {point
                            ? `${point.x.toFixed(2)}, ${point.y.toFixed(2)} m`
                            : "Not saved"}
                          <small>
                            {point
                              ? `${((point.yaw * 180) / Math.PI).toFixed(0)}° heading`
                              : "Choose a destination first"}
                          </small>
                        </span>
                      </div>
                      <div className="waypoint-buttons">
                        <button
                          disabled={!connected}
                          aria-label={`Save waypoint ${name}`}
                          title="Save selected goal"
                          onClick={() =>
                            send({
                              type: "waypoint",
                              action: "save",
                              name,
                              goal,
                            })
                          }
                        >
                          <Save size={14} />
                        </button>
                        <button
                          disabled={
                            !connected || !point || sequence.length >= 12
                          }
                          aria-label={`Add ${name} to sequence`}
                          title="Add to mission sequence"
                          onClick={() => setSequence((old) => [...old, name])}
                        >
                          +
                        </button>
                        <button
                          disabled={!connected || !point || !canPlan}
                          aria-label={`Navigate to waypoint ${name}`}
                          title="Navigate to this waypoint"
                          onClick={() =>
                            send({
                              type: "navigation",
                              action: "sequence",
                              waypoints: [name],
                            })
                          }
                        >
                          <Play size={14} />
                        </button>
                        <button
                          disabled={!connected || !point || active}
                          aria-label={`Delete waypoint ${name}`}
                          title="Delete waypoint"
                          onClick={() =>
                            send({ type: "waypoint", action: "delete", name })
                          }
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
              <label className="sequence-label">
                Mission sequence <span>{sequence.length} / 12</span>
              </label>
              <div className="sequence-list">
                {sequence.length ? (
                  sequence.map((name, index) => (
                    <button
                      key={index}
                      onClick={() =>
                        setSequence((old) => old.filter((_, i) => i !== index))
                      }
                      title="Remove this visit"
                    >
                      {index + 1}. {name} ×
                    </button>
                  ))
                ) : (
                  <span>Add A, B or C in the order to visit.</span>
                )}
              </div>
              <button
                className="run-sequence primary-action"
                disabled={
                  !canPlan ||
                  !sequence.length ||
                  sequence.some((name) => !nav?.waypoints[name])
                }
                onClick={() =>
                  send({
                    type: "navigation",
                    action: "sequence",
                    waypoints: sequence,
                  })
                }
              >
                <Play size={15} />
                Run waypoint sequence
              </button>
            </div>
          </section>
          <div className="navigation-disclaimer">
            <ShieldCheck size={16} />
            <p>
              Educational A* and point follower. Static simulated map; no Nav2,
              TF, LiDAR or hardware connection.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
