import type { SensorBundle } from "./sensors";
export interface Telemetry {
  type: "telemetry";
  simulation: true;
  session_id: string;
  timestamp: string;
  mode: string;
  uptime: number;
  pose: Pose & { frame_id: string };
  home: Pose;
  configuration: RobotConfiguration;
  diagnostics: Diagnostics;
  sensors: Pick<SensorBundle, "lidar" | "camera">;
  clearance: { pose_clear: boolean; radius: number };
  trajectory: [number, number][];
  navigation: NavigationState;
  operations: {
    active: { id: string; status: string } | null;
    queue_count: number;
  };
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
    raw_encoder_count: number;
    tracking_error_rpm: number;
    wheel_velocity: number;
    travel_distance: number;
    source: "simulation";
    pi: {
      source: "unavailable" | "simulation" | "hardware";
      kp: number | null;
      ki: number | null;
      pwm: number | null;
      control_error: number | null;
      integral_term: number | null;
    };
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
  timestamp: string;
  cpu: number;
  ram: number;
  temperature: number;
  battery: number;
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
  status: "idle" | "ready" | "running" | "paused" | "blocked";
  last_result: {
    status: "completed" | "cancelled";
    reason: string;
    progress: number;
    goals: Goal[];
  } | null;
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
export interface RobotConfiguration {
  version: 1;
  home: Goal;
  waypoints: Partial<Record<WaypointName, Goal>>;
  storage: "local-file" | "memory";
  load_warnings: string[];
}
export interface HistoryRecord {
  timestamp: string;
  left_target_rpm: number;
  left_actual_rpm: number;
  right_target_rpm: number;
  right_actual_rpm: number;
  cpu_percent: number;
  memory_percent: number;
  temperature_c: number;
  battery_percent: number;
}
export interface Diagnostics {
  source: "simulation";
  model: string;
  motion: {
    requested: { linear: number; angular: number };
    limited: { linear: number; angular: number };
    measured: { linear: number; angular: number };
  };
  saturation: {
    active: boolean;
    scale: number;
    requested_rpm: number[];
    limit_rpm: number;
  };
  safety: {
    stop_generation?: number;
    stop_active: boolean;
    last_stop_reason: string | null;
    watchdog: string;
    command_age_ms: number | null;
    manual_timeout_ms: number;
    autonomous_timeout_ms: number;
    collision_guard: boolean;
  };
  counters: Record<string, number>;
  interfaces: {
    ros2: {
      source: "disabled";
      connected: false;
      last_message_at: null;
      observed_hz: null;
      diagnostics_contract: string;
      planned: {
        node: string;
        topic: string;
        message_type: string;
        expected_hz: number;
      }[];
    };
    uart: {
      source: "disabled";
      connected: false;
      planned_baud: number;
      last_message_at: null;
      heartbeat: null;
      watchdog: null;
      tx_bytes: null;
      rx_bytes: null;
      command_count: null;
      fault_count: null;
    };
  };
}
export type Command =
  | { type: "operations"; action: "start_next" | "pause" | "resume" | "cancel" }
  | {
      type: "configuration";
      action: "set_home" | "current_home" | "reset_home";
      goal?: Goal;
    }
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
