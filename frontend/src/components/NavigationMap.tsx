import { laserWorldPoints } from "../sensors";
import type { LidarFrame } from "../sensors";
import { useRef, useState } from "react";
import {
  Crosshair,
  Hand,
  Maximize,
  Minus,
  MousePointer2,
  Plus,
} from "lucide-react";
import type { Goal, OccupancyGrid, Telemetry } from "../types";

type Tool = "goal" | "heading" | "pan";
export function NavigationMap({
  grid,
  data,
  selected,
  onSelect,
  disabled,
  lidar,
}: {
  grid: OccupancyGrid;
  data: Telemetry | null;
  selected: Goal | null;
  onSelect: (goal: Goal) => void;
  disabled: boolean;
  lidar: LidarFrame | null;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{
    x: number;
    y: number;
    cx: number;
    cy: number;
    moved: boolean;
  } | null>(null);
  const [tool, setTool] = useState<Tool>("goal");
  const [zoom, setZoom] = useState(1);
  const [center, setCenter] = useState({ x: 4, y: -3 });
  const vw = 9.2 / zoom,
    vh = 6.9 / zoom;
  const points = (list: [number, number][]) =>
    list.map(([x, y]) => `${x},${-y}`).join(" ");
  const heading = selected ?? data?.navigation.destination;
  const pose = data?.pose;
  return (
    <section className="panel map-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">VIRTUAL WAREHOUSE / MAP FRAME</span>
          <h2>Navigation workspace</h2>
        </div>
        <span className="tag">SIMULATED GRID</span>
      </div>
      <div className="map-toolbar">
        <div className="tool-group">
          <button
            className={tool === "goal" ? "active" : ""}
            onClick={() => setTool("goal")}
            title="Click to select destination"
          >
            <MousePointer2 size={15} />
            Destination
          </button>
          <button
            className={tool === "heading" ? "active" : ""}
            onClick={() => setTool("heading")}
            disabled={!selected}
            title="Click a point to aim the selected goal"
          >
            <Crosshair size={15} />
            Heading
          </button>
          <button
            className={tool === "pan" ? "active" : ""}
            onClick={() => setTool("pan")}
          >
            <Hand size={15} />
            Pan
          </button>
        </div>
        <div className="tool-group">
          <button
            aria-label="Zoom in"
            onClick={() => setZoom((z) => Math.min(4, z * 1.25))}
          >
            <Plus size={16} />
          </button>
          <button
            aria-label="Zoom out"
            onClick={() => setZoom((z) => Math.max(0.6, z / 1.25))}
          >
            <Minus size={16} />
          </button>
          <button
            aria-label="Reset map view"
            onClick={() => {
              setZoom(1);
              setCenter({ x: 4, y: -3 });
            }}
          >
            <Maximize size={16} />
          </button>
        </div>
      </div>
      <svg
        ref={svg}
        data-testid="navigation-map"
        className={`navigation-map tool-${tool}`}
        viewBox={`${center.x - vw / 2} ${center.y - vh / 2} ${vw} ${vh}`}
        role="img"
        aria-label="Interactive simulated occupancy map. Click a free area to choose a destination; drag to pan. Numeric destination inputs are also available."
        onPointerDown={(e) => {
          if (e.button !== 0) return;
          svg.current?.setPointerCapture(e.pointerId);
          drag.current = {
            x: e.clientX,
            y: e.clientY,
            cx: center.x,
            cy: center.y,
            moved: false,
          };
        }}
        onPointerMove={(e) => {
          const d = drag.current;
          if (!d || !svg.current) return;
          const dx = e.clientX - d.x,
            dy = e.clientY - d.y;
          if (Math.hypot(dx, dy) > 5) d.moved = true;
          if (d.moved) {
            const rect = svg.current.getBoundingClientRect();
            const scale = Math.max(vw / rect.width, vh / rect.height);
            setCenter({ x: d.cx - dx * scale, y: d.cy - dy * scale });
          }
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
        onPointerUp={(e) => {
          const d = drag.current;
          drag.current = null;
          if (!d || d.moved || tool === "pan" || disabled || !svg.current)
            return;
          const matrix = svg.current.getScreenCTM();
          if (!matrix) return;
          const point = new DOMPoint(e.clientX, e.clientY).matrixTransform(
            matrix.inverse(),
          );
          const x = point.x,
            y = -point.y;
          if (tool === "heading" && selected) {
            onSelect({
              ...selected,
              yaw: Math.atan2(y - selected.y, x - selected.x),
            });
          } else if (x >= 0 && x <= 8 && y >= 0 && y <= 6) {
            onSelect({
              x: Math.round(x * 100) / 100,
              y: Math.round(y * 100) / 100,
              yaw: selected?.yaw ?? 0,
              name: "Destination",
            });
          }
        }}
      >
        <defs>
          <pattern
            id="nav-grid"
            width={grid.resolution}
            height={grid.resolution}
            patternUnits="userSpaceOnUse"
          >
            <path
              d={`M ${grid.resolution} 0 L 0 0 0 ${grid.resolution}`}
              fill="none"
              stroke="var(--map-grid)"
              strokeWidth="0.009"
            />
          </pattern>
          <marker
            id="nav-arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--map-goal)" />
          </marker>
        </defs>
        <rect x="0" y="-6" width="8" height="6" fill="var(--map-surface)" />
        <rect x="0" y="-6" width="8" height="6" fill="url(#nav-grid)" />
        {grid.data.map(
          (value, index) =>
            value !== 0 && (
              <rect
                key={index}
                x={grid.origin.x + (index % grid.width) * grid.resolution}
                y={
                  -grid.origin.y -
                  (Math.floor(index / grid.width) + 1) * grid.resolution
                }
                width={grid.resolution + 0.002}
                height={grid.resolution + 0.002}
                fill={value < 0 ? "var(--map-unknown)" : "var(--map-occupied)"}
                stroke="var(--map-obstacle-border)"
                strokeWidth="0.008"
              />
            ),
        )}
        {Array.from({ length: 9 }, (_, x) => (
          <g key={`x${x}`}>
            <line
              x1={x}
              x2={x}
              y1="0"
              y2="-6"
              stroke="var(--map-grid-major)"
              strokeWidth="0.012"
            />
            <text
              x={x}
              y="0.26"
              textAnchor="middle"
              fill="var(--map-axis)"
              fontSize="0.14"
            >
              {x} m
            </text>
          </g>
        ))}
        {Array.from({ length: 7 }, (_, y) => (
          <g key={`y${y}`}>
            <line
              x1="0"
              x2="8"
              y1={-y}
              y2={-y}
              stroke="var(--map-grid-major)"
              strokeWidth="0.012"
            />
            <text
              x="-0.16"
              y={-y + 0.05}
              textAnchor="end"
              fill="var(--map-axis)"
              fontSize="0.14"
            >
              {y}
            </text>
          </g>
        ))}
        {data && (
          <>
            <polyline
              data-testid="planned-path"
              points={points(data.navigation.path)}
              fill="none"
              stroke="var(--map-path)"
              strokeWidth="0.035"
              strokeDasharray="0.10 0.07"
              strokeLinejoin="round"
            />
            <polyline
              points={points(data.trajectory)}
              fill="none"
              stroke="var(--map-trail)"
              strokeWidth="0.025"
              strokeOpacity=".75"
            />
            <g
              data-testid="home-marker"
              transform={`translate(${data.home.x} ${-data.home.y}) rotate(${(-data.home.yaw * 180) / Math.PI})`}
            >
              <path
                d="M 0 -.21 L .21 0 L 0 .21 L -.21 0 Z"
                fill="var(--map-home-fill)"
                stroke="var(--map-home)"
                strokeWidth=".025"
              />
              <text
                y=".05"
                textAnchor="middle"
                fontSize=".14"
                fill="var(--map-home-text)"
                transform={`rotate(${(data.home.yaw * 180) / Math.PI})`}
              >
                H
              </text>
              <line
                x1=".22"
                x2=".42"
                y1="0"
                y2="0"
                stroke="var(--map-home)"
                strokeWidth=".025"
              />
            </g>
          </>
        )}
        {Object.entries(data?.navigation.waypoints ?? {}).map(
          ([name, p]) =>
            p && (
              <g key={name} transform={`translate(${p.x} ${-p.y})`}>
                <circle
                  r=".14"
                  fill="var(--map-waypoint-fill)"
                  stroke="var(--map-waypoint)"
                  strokeWidth=".02"
                />
                <text
                  textAnchor="middle"
                  y=".05"
                  fontSize=".15"
                  fill="var(--map-waypoint-text)"
                >
                  {name}
                </text>
              </g>
            ),
        )}
        {heading && (
          <g
            transform={`translate(${heading.x} ${-heading.y}) rotate(${(-heading.yaw * 180) / Math.PI})`}
          >
            <circle
              r=".15"
              fill="var(--map-goal-fill)"
              stroke="var(--map-goal)"
              strokeWidth=".025"
            />
            <line
              x1="0"
              y1="0"
              x2=".5"
              y2="0"
              stroke="var(--map-goal)"
              strokeWidth=".025"
              markerEnd="url(#nav-arrow)"
            />
          </g>
        )}
        {lidar && (
          <g data-testid="navigation-lidar-overlay" pointerEvents="none">
            {laserWorldPoints(lidar).map(([x, y], i) => (
              <circle
                key={i}
                cx={x}
                cy={-y}
                r=".025"
                fill="var(--lidar-point)"
                stroke="var(--lidar-point-border)"
                strokeWidth=".006"
              />
            ))}
          </g>
        )}
        {pose && (
          <g
            data-testid="virtual-robot"
            transform={`translate(${pose.x} ${-pose.y}) rotate(${(-pose.yaw * 180) / Math.PI})`}
          >
            <circle
              r={grid.clearance_radius}
              fill="var(--map-clearance-fill)"
              stroke="var(--map-clearance)"
              strokeWidth=".012"
              strokeDasharray=".025 .025"
            />
            <rect
              x="-.125"
              y="-.125"
              width=".25"
              height=".25"
              rx=".04"
              fill="var(--map-robot-fill)"
              stroke="var(--map-robot)"
              strokeWidth=".025"
            />
            <rect
              x="-.07"
              y="-.17"
              width=".14"
              height=".05"
              rx=".01"
              fill="var(--map-wheel)"
            />
            <rect
              x="-.07"
              y=".12"
              width=".14"
              height=".05"
              rx=".01"
              fill="var(--map-wheel)"
            />
            <circle cx="-.08" cy="0" r=".025" fill="var(--map-caster)" />
            <path
              d="M -.01 -.06 L .12 0 L -.01 .06"
              fill="none"
              stroke="var(--map-heading)"
              strokeWidth=".025"
            />
            <line
              x1=".15"
              x2=".38"
              y1="0"
              y2="0"
              stroke="var(--map-robot)"
              strokeWidth=".025"
            />
          </g>
        )}
      </svg>
      <div className="map-legend">
        <span>
          <i className="legend-robot" />
          Virtual AMR
        </span>
        <span>
          <i className="legend-path" />
          Planned path
        </span>
        <span>
          <i className="legend-trail" />
          Trajectory
        </span>
        <span>0.20 m / cell · {Math.round(zoom * 100)}%</span>
      </div>
      <p className="map-hint">
        {tool === "heading"
          ? "Click toward the desired final heading."
          : tool === "pan"
            ? "Drag the map to pan."
            : "Click free space to set a goal. Drag to pan."}{" "}
        Clearance ring includes the chassis and a safety margin.
      </p>
    </section>
  );
}
