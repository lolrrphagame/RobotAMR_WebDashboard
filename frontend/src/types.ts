export interface Telemetry {
  type: "telemetry";
  simulation: true;
  timestamp: string;
  mode: string;
  uptime: number;
  pose: Pose & { frame_id: string };
  home: Pose;
  trajectory: [number, number][];
  navigation: NavigationState;
  drive: {
    max_rpm: number;
    chassis_size: number;
    encoder_polarity: [number, number];
  };
  linear_velocity: number;
  angular_velocity: number;
  motors: {
    name: string;
    target_rpm: number;
    actual_rpm: number;
    encoder_count: number;
  }[];
  health: {
    cpu_percent: number;
    temperature_c: number;
    memory_percent: number;
    battery_percent: number;
    battery_voltage: number;
  };
  events: { id: number; time: string; level: string; message: string }[];
}
export interface Sample {
  time: string;
  leftTarget: number;
  leftActual: number;
  rightTarget: number;
  rightActual: number;
}
export interface Pose {
  x: number;
  y: number;
  yaw: number;
}
export interface Goal extends Pose {
  name?: string;
}
export type WaypointName = "A" | "B" | "C";
export interface NavigationState {
  status:
    | "idle"
    | "ready"
    | "running"
    | "paused"
    | "completed"
    | "cancelled"
    | "blocked";
  progress: number;
  reason: string;
  destination: Goal | null;
  current_waypoint: string | null;
  waypoint_index: number;
  waypoint_count: number;
  path: [number, number][];
  waypoints: Partial<Record<WaypointName, Goal>>;
}
export interface OccupancyGrid {
  id: string;
  frame_id: string;
  width: number;
  height: number;
  resolution: number;
  origin: Pose;
  data: number[];
  clearance_radius: number;
}
export type Command =
  | {
      type: "control" | "stop" | "release" | "heartbeat";
      linear?: number;
      angular?: number;
    }
  | {
      type: "navigation";
      action:
        "plan" | "start" | "pause" | "resume" | "cancel" | "home" | "sequence";
      goal?: Goal;
      waypoints?: WaypointName[];
    }
  | {
      type: "waypoint";
      action: "save" | "delete";
      name: WaypointName;
      goal?: Goal;
    };
