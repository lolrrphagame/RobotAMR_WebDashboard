import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Command } from "../types";
import { downloadCsv, formatTimestamp } from "../utils/telemetry";
type Step = {
  kind: "waypoint" | "pose" | "home" | "wait";
  waypoint?: string;
  pose?: { x: number; y: number; yaw: number };
  seconds?: number;
};
type Definition = { name: string; steps: Step[] };
type Pending = {
  id: string;
  name: string;
  created_at: string;
  definition: Definition;
};
type Run = {
  id: string;
  name: string;
  status: string;
  steps: (Step & { status: string })[];
  current_step: number;
  completed_steps: number;
  progress: number;
  started_at: string;
  finished_at: string | null;
  duration: number;
  distance: number;
  reason: string | null;
  wait_remaining: number;
};
type Analytics = {
  total: number;
  completed: number;
  cancelled: number;
  failed: number;
  interrupted: number;
  success_rate: number;
  average_duration: number;
  distance: number;
  waypoint_visits: number;
  trends: { date: string; missions: number }[];
};
type State = {
  active: Run | null;
  queue: Pending[];
  templates: Pending[];
  analytics: Analytics;
  history: Run[];
};
const describe = (s: Step) =>
  s.kind === "wait"
    ? `WAIT ${s.seconds}s`
    : s.kind === "home"
      ? "Return to saved Home"
      : s.kind === "waypoint"
        ? `Waypoint ${s.waypoint}`
        : `Pose ${s.pose?.x}, ${s.pose?.y} / ${(((s.pose?.yaw ?? 0) * 180) / Math.PI).toFixed(0)}°`;
export function MissionOverview({ state }: { state: State | null }) {
  return (
    <div className="mission-overview">
      {[
        ["Active", state?.active?.status ?? "Idle"],
        ["Pending", state?.queue.length ?? 0],
        ["Completed", state?.analytics.completed ?? 0],
        ["Success rate", `${state?.analytics.success_rate.toFixed(1) ?? 0}%`],
      ].map(([label, value]) => (
        <section className="panel" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </section>
      ))}
    </div>
  );
}
export function ActiveMission({
  run,
  send,
  connected,
}: {
  run: Run | null;
  send: (c: Command) => void;
  connected: boolean;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Active mission</h2>
        <span className="tag">SIMULATION</span>
      </div>
      <div className="nav-body">
        {run ? (
          <>
            <h3>{run.name}</h3>
            <p data-testid="operation-status">
              {run.status.toUpperCase()} · step{" "}
              {Math.min(run.current_step + 1, run.steps.length)} /{" "}
              {run.steps.length}
            </p>
            <progress
              max="100"
              value={run.progress}
              aria-label="Operations mission progress"
            />
            <p>
              {run.completed_steps} completed · {run.progress.toFixed(0)}% ·{" "}
              {run.duration.toFixed(1)} s · {run.distance.toFixed(2)} m
            </p>
            {run.reason && <p className="home-locked">{run.reason}</p>}
            <ol>
              {run.steps.map((step, i) => (
                <li key={i}>
                  {describe(step)} · {step.status}
                </li>
              ))}
            </ol>
            <div className="mission-actions">
              <button
                disabled={!connected || run.status !== "running"}
                onClick={() => send({ type: "operations", action: "pause" })}
              >
                Pause mission
              </button>
              <button
                disabled={!connected || run.status !== "paused"}
                onClick={() => send({ type: "operations", action: "resume" })}
              >
                Resume mission
              </button>
              <button
                onClick={() => send({ type: "operations", action: "cancel" })}
              >
                Cancel active mission
              </button>
            </div>
          </>
        ) : (
          <p>
            No active mission. Queue execution requires an explicit Start next
            command.
          </p>
        )}
      </div>
    </section>
  );
}
export function MissionBuilder({
  create,
}: {
  create: (d: Definition, template: boolean) => Promise<void>;
}) {
  const [name, setName] = useState("Station delivery");
  const [steps, setSteps] = useState<Step[]>([]);
  const [kind, setKind] = useState<Step["kind"]>("waypoint");
  const [waypoint, setWaypoint] = useState("A");
  const [seconds, setSeconds] = useState(2);
  const [x, setX] = useState(2);
  const [y, setY] = useState(1);
  const [yaw, setYaw] = useState(0);
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Mission builder</h2>
        <span className="tag">DEFINITION ONLY</span>
      </div>
      <div className="nav-body mission-builder">
        <label>
          Mission name
          <input
            aria-label="Mission name"
            value={name}
            maxLength={80}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          Step type
          <select
            aria-label="Mission step type"
            value={kind}
            onChange={(e) => setKind(e.target.value as Step["kind"])}
          >
            <option value="waypoint">Saved waypoint</option>
            <option value="pose">Map pose</option>
            <option value="home">Return Home</option>
            <option value="wait">WAIT at station</option>
          </select>
        </label>
        {kind === "waypoint" && (
          <label>
            Waypoint
            <select
              aria-label="Mission waypoint"
              value={waypoint}
              onChange={(e) => setWaypoint(e.target.value)}
            >
              {["A", "B", "C"].map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
        )}
        {kind === "wait" && (
          <label>
            WAIT duration (seconds)
            <input
              aria-label="WAIT duration"
              type="number"
              min="0.1"
              max="3600"
              step=".1"
              value={seconds}
              onChange={(e) => setSeconds(Number(e.target.value))}
            />
          </label>
        )}
        {kind === "pose" && (
          <div className="goal-coordinates">
            {[
              ["X (m)", x, setX],
              ["Y (m)", y, setY],
              ["Heading (degrees)", yaw, setYaw],
            ].map(([label, value, setter]) => (
              <label key={String(label)}>
                {String(label)}
                <input
                  aria-label={`Mission ${label}`}
                  type="number"
                  value={value as number}
                  onChange={(e) =>
                    (setter as (n: number) => void)(Number(e.target.value))
                  }
                />
              </label>
            ))}
          </div>
        )}
        <button
          disabled={steps.length >= 32}
          onClick={() =>
            setSteps((old) => [
              ...old,
              kind === "wait"
                ? { kind, seconds }
                : kind === "waypoint"
                  ? { kind, waypoint }
                  : kind === "pose"
                    ? { kind, pose: { x, y, yaw: (yaw * Math.PI) / 180 } }
                    : { kind },
            ])
          }
        >
          Add step
        </button>
        <ol>
          {steps.map((s, i) => (
            <li key={i}>
              {describe(s)}{" "}
              <button
                aria-label={`Remove step ${i + 1}`}
                onClick={() => setSteps((old) => old.filter((_, n) => n !== i))}
              >
                ×
              </button>
              {i > 0 && (
                <button
                  aria-label={`Move step ${i + 1} up`}
                  onClick={() =>
                    setSteps((old) => {
                      const a = [...old];
                      [a[i - 1], a[i]] = [a[i], a[i - 1]];
                      return a;
                    })
                  }
                >
                  Move up
                </button>
              )}
            </li>
          ))}
        </ol>
        <div className="mission-actions">
          <button
            disabled={!name.trim() || !steps.length}
            onClick={() => void create({ name, steps }, false)}
          >
            Add mission to queue
          </button>
          <button
            disabled={!name.trim() || !steps.length}
            onClick={() => void create({ name, steps }, true)}
          >
            Save mission template
          </button>
        </div>
        <p>Up to 32 steps. Saving or queuing never starts motion.</p>
      </div>
    </section>
  );
}
export function MissionQueue({
  state,
  action,
  send,
  connected,
}: {
  state: State;
  action: (url: string, method: string, body?: unknown) => Promise<void>;
  send: (c: Command) => void;
  connected: boolean;
}) {
  const [confirm, setConfirm] = useState(false);
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Pending queue</h2>
        <span className="tag">{state.queue.length} / 20</span>
      </div>
      <div className="nav-body">
        <div className="mission-actions">
          <button
            disabled={!connected || !!state.active || !state.queue.length}
            onClick={() => send({ type: "operations", action: "start_next" })}
          >
            Start next mission
          </button>
          <button
            disabled={!state.queue.length}
            onClick={() => setConfirm(true)}
          >
            Clear queue
          </button>
        </div>
        {confirm && (
          <div className="connection-alert">
            Remove all pending definitions? Active motion is unaffected.
            <button
              onClick={() => {
                void action("/api/missions/queue?confirm=true", "DELETE");
                setConfirm(false);
              }}
            >
              Confirm clear queue
            </button>
            <button onClick={() => setConfirm(false)}>Keep queue</button>
          </div>
        )}
        {!state.queue.length && (
          <p>Queue empty. Create a mission or queue a saved template.</p>
        )}
        {state.queue.map((item, i) => (
          <div className="mission-queue-item" key={item.id}>
            <strong>
              {i + 1}. {item.name}
            </strong>
            <details>
              <summary>{item.definition.steps.length} steps · details</summary>
              <ol>
                {item.definition.steps.map((step, n) => (
                  <li key={n}>{describe(step)}</li>
                ))}
              </ol>
            </details>
            <div className="mission-actions">
              <button
                disabled={i === 0}
                aria-label={`Move ${item.name} up`}
                onClick={() => {
                  const ids = state.queue.map((v) => v.id);
                  [ids[i - 1], ids[i]] = [ids[i], ids[i - 1]];
                  void action("/api/missions/queue/order", "POST", ids);
                }}
              >
                Move up
              </button>
              <button
                onClick={() =>
                  void action(`/api/missions/${item.id}`, "DELETE")
                }
              >
                Remove pending mission
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
export function MissionAnalytics({ analytics: a }: { analytics: Analytics }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Operational analytics</h2>
        <span className="tag">STORED SIMULATION RECORDS</span>
      </div>
      {!a.total ? (
        <p className="nav-body">
          No completed execution history yet. Metrics will come from stored
          mission outcomes.
        </p>
      ) : (
        <>
          <div className="detail-grid">
            {[
              ["Total missions", a.total],
              ["Completed", a.completed],
              ["Cancelled", a.cancelled],
              ["Failed", a.failed],
              ["Interrupted", a.interrupted],
              ["Success rate", `${a.success_rate.toFixed(1)}%`],
              ["Mean active duration", `${a.average_duration.toFixed(1)} s`],
              ["Estimated path travel", `${a.distance.toFixed(2)} m`],
              ["Waypoint visits", a.waypoint_visits],
            ].map(([label, v]) => (
              <div key={label}>
                {label}
                <strong>{v}</strong>
              </div>
            ))}
          </div>
          <div className="health-history-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={a.trends}>
                <CartesianGrid stroke="var(--chart-grid)" />
                <XAxis dataKey="date" stroke="var(--chart-axis)" />
                <YAxis allowDecimals={false} stroke="var(--chart-axis)" />
                <Tooltip
                  cursor={{ fill: "var(--chart-cursor)" }}
                  labelStyle={{ color: "var(--text-primary)" }}
                  contentStyle={{
                    background: "var(--chart-tooltip)",
                    border: "1px solid var(--chart-tooltip-border)",
                    borderRadius: 8,
                  }}
                />
                <Bar dataKey="missions" fill="var(--chart-left)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </section>
  );
}
export function MissionHistory({
  records,
  status,
  setStatus,
  query,
  setQuery,
}: {
  records: Run[];
  status: string;
  setStatus: (s: string) => void;
  query: string;
  setQuery: (s: string) => void;
}) {
  const [error, setError] = useState("");
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Mission history</h2>
        <span className="tag">PERSISTENT SQLITE</span>
      </div>
      <div className="event-toolbar">
        <label>
          Result
          <select
            aria-label="Mission history result"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            {["all", "completed", "cancelled", "failed", "interrupted"].map(
              (s) => (
                <option key={s}>{s}</option>
              ),
            )}
          </select>
        </label>
        <label>
          Search
          <input
            aria-label="Search mission history"
            value={query}
            maxLength={200}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <button
          onClick={() =>
            void downloadCsv(
              `/api/missions/history?${new URLSearchParams({ status, q: query, format: "csv" })}`,
              "pbl4-missions.csv",
            ).catch((e) => setError(String(e)))
          }
        >
          Export mission history CSV
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      <div className="diagnostic-table-wrap">
        <table className="diagnostic-table">
          <thead>
            <tr>
              <th>Mission / started</th>
              <th>Result</th>
              <th>Duration</th>
              <th>Distance</th>
              <th>Completed steps / details</th>
            </tr>
          </thead>
          <tbody>
            {records.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.name}
                  <small className="block">
                    {formatTimestamp(r.started_at)}
                  </small>
                </td>
                <td>
                  {r.status}
                  <small className="block">{r.reason}</small>
                </td>
                <td>{r.duration.toFixed(1)} s</td>
                <td>{r.distance.toFixed(2)} m</td>
                <td>
                  <details>
                    <summary>
                      {r.completed_steps} / {r.steps.length}
                    </summary>
                    {r.steps.map((s, i) => (
                      <p key={i}>
                        {describe(s)} · {s.status}
                      </p>
                    ))}
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!records.length && (
          <p className="nav-body">No matching mission history.</p>
        )}
      </div>
    </section>
  );
}
export function MissionsPage({
  send,
  connected,
}: {
  send: (c: Command) => void;
  connected: boolean;
}) {
  const [state, setState] = useState<State | null>(null);
  const [records, setRecords] = useState<Run[]>([]);
  const [status, setStatus] = useState("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let disposed = false;
    let loading = false;
    let activeController: AbortController | null = null;
    const load = async () => {
      if (disposed || loading) return;
      loading = true;
      const controller = new AbortController();
      activeController = controller;
      try {
        const [a, b] = await Promise.all([
          fetch("/api/missions", { signal: controller.signal }),
          fetch(
            `/api/missions/history?${new URLSearchParams({ status, q: query })}`,
            { signal: controller.signal },
          ),
        ]);
        if (!a.ok || !b.ok) throw Error("Mission service unavailable");
        const [s, h] = await Promise.all([a.json(), b.json()]);
        if (!disposed) {
          setState(s);
          setRecords(h.records);
          setLoadError("");
        }
      } catch (e) {
        controller.abort(); // Abort the other leg if either parallel request fails.
        if (!disposed) setLoadError(String(e));
      } finally {
        loading = false;
        if (activeController === controller) activeController = null;
      }
    };
    void load();
    const timer = setInterval(() => void load(), 1000);
    return () => {
      disposed = true;
      activeController?.abort();
      clearInterval(timer);
    };
  }, [version, status, query]);
  const action = async (url: string, method: string, body?: unknown) => {
    if (!connected) {
      setError("Operator authentication and connection required");
      return;
    }
    try {
      const r = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!r.ok) {
        const e = await r.json();
        throw Error(
          typeof e.detail === "string"
            ? e.detail
            : "Invalid mission definition; check steps and destinations",
        );
      }
      setVersion((n) => n + 1);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  };
  const create = (d: Definition, template: boolean) =>
    action(`/api/missions?template=${template}`, "POST", d);
  return (
    <div className="missions-page">
      <div className="diagnostics-notice">
        SIMULATION OPERATIONS · One robot, one navigation controller. No queued
        mission auto-starts after completion, STOP, disconnect or restart.
      </div>
      {(error || loadError) && (
        <div role="alert" className="connection-alert">
          {error || loadError}
        </div>
      )}
      <MissionOverview state={state} />
      <ActiveMission
        run={state?.active ?? null}
        send={send}
        connected={connected && !loadError}
      />
      <div className="mission-columns">
        <fieldset disabled={!connected}>
          <MissionBuilder create={create} />
        </fieldset>
        {state && (
          <MissionQueue
            state={state}
            action={action}
            send={send}
            connected={connected && !loadError}
          />
        )}
      </div>
      {state && (
        <>
          <section className="panel">
            <div className="panel-heading">
              <h2>Saved mission templates</h2>
            </div>
            <div className="nav-body">
              {!state.templates.length && (
                <p>No templates saved. Templates never launch automatically.</p>
              )}
              {state.templates.map((t) => (
                <div className="mission-queue-item" key={t.id}>
                  <strong>{t.name}</strong>
                  <p>{t.definition.steps.map(describe).join(" · ")}</p>
                  <div className="mission-actions">
                    <button onClick={() => void create(t.definition, false)}>
                      Queue template
                    </button>
                    <button
                      onClick={() =>
                        void action(
                          `/api/missions/${t.id}?template=true`,
                          "DELETE",
                        )
                      }
                    >
                      Delete template
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
          <MissionAnalytics analytics={state.analytics} />
        </>
      )}
      <MissionHistory
        records={records}
        status={status}
        setStatus={setStatus}
        query={query}
        setQuery={setQuery}
      />
    </div>
  );
}
