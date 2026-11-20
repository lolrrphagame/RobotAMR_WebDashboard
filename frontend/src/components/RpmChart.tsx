import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Sample } from "../types";
export function RpmChart({
  history,
  motor,
  windowLabel = "Last 15 seconds",
}: {
  history: Sample[];
  motor: "left" | "right";
  windowLabel?: string;
}) {
  const color = motor === "left" ? "#25d9e8" : "#8d9bff";
  return (
    <section className="panel chart-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">
            WHEEL SPEED / {motor === "left" ? "M1" : "M2"}
          </span>
          <h2>{motor === "left" ? "Left" : "Right"} motor response</h2>
        </div>
        <span className="unit">RPM</span>
      </div>
      <div className="chart-legend">
        <span>
          <i style={{ background: color }} />
          Actual RPM
        </span>
        <span>
          <i className="dashed" />
          Target RPM
        </span>
        <span className="ml-auto text-slate-400">{windowLabel}</span>
      </div>
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={history}
            margin={{ top: 12, right: 10, left: -22, bottom: 0 }}
          >
            <CartesianGrid
              stroke="#223047"
              strokeDasharray="3 5"
              vertical={false}
            />
            <XAxis
              dataKey="time"
              minTickGap={75}
              stroke="#8191ab"
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              domain={[-45, 45]}
              ticks={[-40, -20, 0, 20, 40]}
              stroke="#8191ab"
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                background: "#121e30",
                border: "1px solid #304059",
                borderRadius: 10,
              }}
            />
            <Line
              name="Target RPM"
              type="monotone"
              dataKey={`${motor}Target`}
              stroke="#a6b2c7"
              strokeDasharray="5 5"
              dot={false}
              isAnimationActive={false}
            />
            <Line
              name="Actual RPM"
              type="monotone"
              dataKey={`${motor}Actual`}
              stroke={color}
              strokeWidth={2.5}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
