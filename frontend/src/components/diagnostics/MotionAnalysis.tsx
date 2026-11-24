import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Sample } from "../../types";
import { bodyTrackingError, trackingStats } from "../../utils/motionAnalysis";
import {
  formatTime,
  historyWindow,
  withHistoryGaps,
} from "../../utils/telemetry";

const series = {
  linear: [
    {
      key: "requestedLinear",
      name: "Requested",
      color: "var(--chart-target)",
      dash: "5 4",
    },
    {
      key: "limitedLinear",
      name: "Limited",
      color: "var(--chart-right)",
      dash: "2 3",
    },
    { key: "measuredLinear", name: "Measured", color: "var(--chart-left)" },
  ],
  angular: [
    {
      key: "requestedAngular",
      name: "Requested",
      color: "var(--chart-target)",
      dash: "5 4",
    },
    {
      key: "limitedAngular",
      name: "Limited",
      color: "var(--chart-right)",
      dash: "2 3",
    },
    { key: "measuredAngular", name: "Measured", color: "var(--chart-left)" },
  ],
  wheel: [
    { key: "leftError", name: "Left wheel", color: "var(--chart-left)" },
    {
      key: "rightError",
      name: "Right wheel",
      color: "var(--chart-right)",
      dash: "5 4",
    },
  ],
} as const;
const minimumExtent = { linear: 0.02, angular: 0.1, wheel: 1 };

function MotionChart({
  title,
  unit,
  kind,
  history,
  domain,
}: {
  title: string;
  unit: string;
  kind: keyof typeof series;
  history: ReturnType<typeof withHistoryGaps>;
  domain: [number, number];
}) {
  const lines = series[kind];
  let extent = minimumExtent[kind];
  let hasSamples = false;
  for (const row of history) {
    for (const { key } of lines) {
      const value = row[key];
      if (value == null) continue;
      extent = Math.max(extent, 1.12 * Math.abs(value));
      hasSamples = true;
    }
  }
  const step = 10 ** Math.floor(Math.log10(extent)) / 2;
  const axisMax = Math.ceil(extent / step) * step;
  const ticks = [-axisMax, -axisMax / 2, 0, axisMax / 2, axisMax];
  return (
    <section className="panel chart-panel motion-chart" aria-label={title}>
      <div className="panel-heading">
        <h3>{title}</h3>
        <span className="unit">{unit}</span>
      </div>
      <div className="chart-legend">
        {lines.map(({ name, color, ...line }) => (
          <span key={name}>
            <i
              className="motion-series-swatch"
              style={{
                borderTopColor: color,
                borderTopStyle: "dash" in line ? "dashed" : "solid",
              }}
            />
            {name}
          </span>
        ))}
      </div>
      {!hasSamples ? (
        <p className="motion-chart-empty">No valid samples in this window.</p>
      ) : (
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={history}
              margin={{ top: 12, right: 12, left: 2, bottom: 0 }}
            >
              <CartesianGrid
                stroke="var(--chart-grid)"
                strokeDasharray="3 5"
                vertical={false}
              />
              <XAxis
                dataKey="epochMs"
                type="number"
                domain={domain}
                allowDataOverflow
                tickFormatter={formatTime}
                minTickGap={24}
                tickCount={5}
                stroke="var(--chart-axis)"
                tick={{ fontSize: 11 }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                width={53}
                domain={[-axisMax, axisMax]}
                ticks={ticks}
                allowDataOverflow
                tickFormatter={(value: number) =>
                  String(Number(value.toFixed(3)))
                }
                stroke="var(--chart-axis)"
                tick={{ fontSize: 11 }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                labelFormatter={(value) => formatTime(Number(value))}
                formatter={(value) =>
                  typeof value === "number"
                    ? `${value.toFixed(kind === "wheel" ? 2 : 4)} ${unit}`
                    : value
                }
                cursor={{ stroke: "var(--chart-axis)", strokeDasharray: "3 3" }}
                labelStyle={{ color: "var(--text-primary)" }}
                contentStyle={{
                  background: "var(--chart-tooltip)",
                  border: "1px solid var(--chart-tooltip-border)",
                  borderRadius: 8,
                }}
              />
              {kind === "wheel" && (
                <ReferenceLine
                  y={0}
                  stroke="var(--chart-axis)"
                  strokeDasharray="4 3"
                />
              )}
              {lines.map(({ key, name, color, ...line }) => (
                <Line
                  key={key}
                  name={name}
                  dataKey={key}
                  stroke={color}
                  strokeWidth={2}
                  strokeDasharray={"dash" in line ? line.dash : undefined}
                  dot={({ cx, cy, index }) => {
                    const indexValue = (offset: number) =>
                      history[index + offset]?.[key] != null;
                    return cx != null &&
                      cy != null &&
                      !indexValue(-1) &&
                      !indexValue(1) ? (
                      <circle key={index} cx={cx} cy={cy} r={2} fill={color} />
                    ) : null;
                  }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}

const channels = [
  { label: "Left wheel", unit: "RPM", error: (s: Sample) => s.leftError },
  { label: "Right wheel", unit: "RPM", error: (s: Sample) => s.rightError },
  {
    label: "Body linear velocity",
    unit: "m/s",
    error: (s: Sample) => bodyTrackingError(s.limitedLinear, s.measuredLinear),
  },
  {
    label: "Body angular velocity",
    unit: "rad/s",
    error: (s: Sample) =>
      bodyTrackingError(s.limitedAngular, s.measuredAngular),
  },
];

export function MotionAnalysis({ history }: { history: Sample[] }) {
  const [seconds, setSeconds] = useState(30);
  const samples = useMemo(
    () => historyWindow(history, seconds),
    [history, seconds],
  );
  const chartHistory = useMemo(() => withHistoryGaps(samples), [samples]);
  const end = samples.at(-1)?.epochMs ?? 0;
  const domain: [number, number] = [end - seconds * 1000, end];
  return (
    <>
      <div className="motion-analysis-toolbar">
        <div>
          <h2>Live motion analysis</h2>
          <p className="muted">
            {samples.length} retained samples in this window
          </p>
        </div>
        <label>
          History window
          <select
            value={seconds}
            onChange={(event) => setSeconds(Number(event.target.value))}
          >
            {[10, 30, 60].map((value) => (
              <option key={value} value={value}>
                {value} seconds
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="diagnostics-notice motion-comparisons">
        <span>
          <strong>Command limiting</strong> · Requested vs limited body velocity
        </span>
        <span>
          <strong>Motion tracking</strong> · Limited vs simulated measured body
          velocity
        </span>
        <span>
          <strong>Wheel tracking</strong> · Target minus actual RPM
        </span>
      </p>
      <div className="motor-diagnostics-grid motion-chart-grid">
        <MotionChart
          title="Linear velocity"
          unit="m/s"
          kind="linear"
          history={chartHistory}
          domain={domain}
        />
        <MotionChart
          title="Angular velocity"
          unit="rad/s"
          kind="angular"
          history={chartHistory}
          domain={domain}
        />
      </div>
      <MotionChart
        title="Signed wheel tracking error"
        unit="RPM"
        kind="wheel"
        history={chartHistory}
        domain={domain}
      />
      <section className="panel" aria-labelledby="tracking-statistics-title">
        <div className="panel-heading">
          <h3 id="tracking-statistics-title">Tracking error statistics</h3>
        </div>
        <div className="diagnostic-table-wrap">
          <table className="diagnostic-table motion-statistics">
            <thead>
              <tr>
                <th scope="col">Signal</th>
                <th scope="col">Samples</th>
                <th scope="col">
                  <abbr title="Mean absolute error">MAE</abbr>
                </th>
                <th scope="col">
                  <abbr title="Root mean square error">RMSE</abbr>
                </th>
                <th scope="col">Max absolute error</th>
              </tr>
            </thead>
            <tbody>
              {channels.map(({ label, unit, error }) => {
                const stats = trackingStats(samples, error);
                const precision = unit === "RPM" ? 2 : 4;
                return (
                  <tr key={label}>
                    <th scope="row">
                      {label} <small>({unit})</small>
                    </th>
                    <td>{stats?.count ?? 0}</td>
                    {stats ? (
                      <>
                        <td>{stats.mae.toFixed(precision)}</td>
                        <td>{stats.rmse.toFixed(precision)}</td>
                        <td>{stats.max.toFixed(precision)}</td>
                      </>
                    ) : (
                      <td colSpan={3}>Unavailable</td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="diagnostic-footnote">
          Each statistic uses available samples for that signal, including valid
          zero errors.
        </p>
      </section>
    </>
  );
}
