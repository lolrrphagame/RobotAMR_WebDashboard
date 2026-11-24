import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Sample } from "../../types";
import { withHistoryGaps } from "../../utils/telemetry";
export function SystemHealth({ history }: { history: Sample[] }) {
  const chartHistory = withHistoryGaps(history);
  return (
    <>
      <div className="diagnostics-notice">
        SIMULATED SYSTEM HEALTH · Synthetic readings, not Raspberry Pi or
        battery sensor measurements.
      </div>
      <div className="system-history-grid">
        {[
          {
            key: "cpu",
            label: "CPU load",
            unit: "%",
            max: 100,
            color: "var(--chart-left)",
          },
          {
            key: "ram",
            label: "RAM usage",
            unit: "%",
            max: 100,
            color: "var(--chart-right)",
          },
          {
            key: "temperature",
            label: "CPU temperature",
            unit: "°C",
            max: 85,
            color: "var(--warning)",
          },
          {
            key: "battery",
            label: "Battery level",
            unit: "%",
            max: 100,
            color: "var(--success)",
          },
        ].map(({ key, label, unit, max, color }) => (
          <section className="panel" key={key}>
            <div className="panel-heading">
              <h2>{label}</h2>
              <span className="tag">SIMULATED / {unit}</span>
            </div>
            <div className="health-history-chart">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={chartHistory}
                  margin={{ top: 20, right: 20, left: -12, bottom: 5 }}
                >
                  <CartesianGrid
                    stroke="var(--chart-grid)"
                    strokeDasharray="3 5"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="time"
                    minTickGap={80}
                    tick={{ fontSize: 11, fill: "var(--chart-axis)" }}
                    stroke="var(--chart-axis)"
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    domain={[0, max]}
                    tick={{ fontSize: 11, fill: "var(--chart-axis)" }}
                    stroke="var(--chart-axis)"
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    position={{ y: 0 }}
                    cursor={{
                      stroke: "var(--chart-axis)",
                      strokeDasharray: "3 3",
                    }}
                    labelStyle={{ color: "var(--text-primary)" }}
                    contentStyle={{
                      background: "var(--chart-tooltip)",
                      border: "1px solid var(--chart-tooltip-border)",
                      borderRadius: 8,
                    }}
                  />
                  <Line
                    name={`${label} (${unit})`}
                    dataKey={key}
                    stroke={color}
                    strokeWidth={2}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>
        ))}
      </div>
      <p className="diagnostic-footnote">
        Up to 600 samples / approximately 60 seconds. Historical values remain
        historical if the stream disconnects; live readings are hidden.
      </p>
    </>
  );
}
