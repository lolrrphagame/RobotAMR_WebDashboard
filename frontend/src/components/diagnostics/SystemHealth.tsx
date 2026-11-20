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
export function SystemHealth({ history }: { history: Sample[] }) {
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
            color: "#39d5e7",
          },
          {
            key: "ram",
            label: "RAM usage",
            unit: "%",
            max: 100,
            color: "#9aabff",
          },
          {
            key: "temperature",
            label: "CPU temperature",
            unit: "°C",
            max: 85,
            color: "#e9b56a",
          },
          {
            key: "battery",
            label: "Battery level",
            unit: "%",
            max: 100,
            color: "#42d2a4",
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
                  data={history}
                  margin={{ top: 20, right: 20, left: -12, bottom: 5 }}
                >
                  <CartesianGrid
                    stroke="#24364f"
                    strokeDasharray="3 5"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="time"
                    minTickGap={80}
                    tick={{ fontSize: 11 }}
                    stroke="#7a94b3"
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    domain={[0, max]}
                    tick={{ fontSize: 11 }}
                    stroke="#7a94b3"
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#142239",
                      border: "1px solid #344760",
                      borderRadius: 8,
                    }}
                  />
                  <Line
                    name={`${label} (${unit})`}
                    dataKey={key}
                    stroke={color}
                    strokeWidth={2}
                    dot={false}
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
