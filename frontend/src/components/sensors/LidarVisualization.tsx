import type { LidarFrame } from "../../sensors";
export function LidarVisualization({
  frame,
  ready,
}: {
  frame: LidarFrame | null;
  ready: boolean;
}) {
  const max = frame?.metadata.range_max ?? 5;
  const point = (angle: number, range: number) => ({
    x: -range * Math.sin(angle),
    y: -range * Math.cos(angle),
  });
  return (
    <svg
      className="lidar-polar"
      data-testid="lidar-polar"
      viewBox={`${-max - 0.7} ${-max - 0.7} ${2 * max + 1.4} ${max + 1.6}`}
      role="img"
      aria-label="Simulated 180 degree laser scan, forward up and positive angles to the left"
    >
      <defs>
        <radialGradient id="lidar-glow">
          <stop offset="0%" stopColor="var(--lidar-glow)" stopOpacity=".35" />
          <stop
            offset="100%"
            stopColor="var(--lidar-glow-end)"
            stopOpacity=".2"
          />
        </radialGradient>
      </defs>
      <path
        d={`M ${-max} 0 A ${max} ${max} 0 0 1 ${max} 0 L 0 0 Z`}
        fill="url(#lidar-glow)"
      />
      {[1, 2, 3, 4, 5]
        .filter((r) => r <= max)
        .map((r) => (
          <g key={r}>
            <path
              d={`M ${-r} 0 A ${r} ${r} 0 0 1 ${r} 0`}
              fill="none"
              stroke="var(--lidar-grid)"
              strokeWidth=".014"
              strokeDasharray=".04 .06"
            />
            <text x=".1" y={-r + 0.18} fill="var(--lidar-axis)" fontSize=".14">
              {r} m
            </text>
          </g>
        ))}
      {[-90, -60, -30, 0, 30, 60, 90].map((deg) => {
        const p = point((deg * Math.PI) / 180, max);
        return (
          <g key={deg}>
            <line
              x1="0"
              y1="0"
              x2={p.x}
              y2={p.y}
              stroke="var(--lidar-grid)"
              strokeWidth=".014"
            />
            <text
              x={p.x * 1.075}
              y={p.y * 1.075 - 0.02}
              fill="var(--lidar-axis)"
              fontSize=".16"
              textAnchor="middle"
            >
              {deg === 0 ? "0° · FORWARD" : `${deg > 0 ? "+" : ""}${deg}°`}
            </text>
          </g>
        );
      })}
      {ready && frame?.payload && (
        <g data-testid="lidar-returns">
          {frame.payload.ranges.map((range, i) => {
            if (!frame.payload?.hits[i]) return null;
            const p = point(
              frame.metadata.angle_min + i * frame.metadata.angle_increment,
              range,
            );
            return (
              <g key={i}>
                {i % 10 === 0 && (
                  <line
                    x1="0"
                    y1="0"
                    x2={p.x}
                    y2={p.y}
                    stroke="var(--lidar-ray)"
                    strokeWidth=".012"
                    opacity=".17"
                  />
                )}
                <circle cx={p.x} cy={p.y} r=".031" fill="var(--lidar-point)" />
              </g>
            );
          })}
        </g>
      )}
      <path d="M 0 -.16 L .12 .10 L -.12 .10 Z" fill="var(--map-robot)" />
      <text
        x="0"
        y=".42"
        fill="var(--lidar-axis)"
        fontSize=".16"
        textAnchor="middle"
      >
        VIRTUAL LASER · ROBOT FRAME
      </text>
      {!ready && (
        <text
          x="0"
          y={-max / 2}
          textAnchor="middle"
          fill="var(--warning)"
          fontSize=".22"
        >
          No fresh simulated scan
        </text>
      )}
    </svg>
  );
}
