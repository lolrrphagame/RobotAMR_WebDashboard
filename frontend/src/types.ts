import type { SensorBundle } from "./sensors";
export type MotionAuthority = "STANDBY" | "MANUAL" | "AUTONOMOUS";

export interface Telemetry {
  type: "telemetry";
  simulation: true;
  session_id: string;
  timestamp: string;
  mode: MotionAuthority;
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
    active: {
      id: string;
      name: string;
      status: "running" | "paused";
      progress: number;
      reason: string | null;
      current_step: number;
      steps: { kind: "waypoint" | "home" | "pose" | "wait" }[];
    } | null;
    queue_count: number;
  };
  drive: {
    max_rpm: number;
    wheel_radius: number;
    wheel_separation: number;
    encoder_cpr: number;
    acceleration_rpm_s: number;
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
  sessionId: string;
  epochMs: number;
  cpu: number | null;
  ram: number | null;
  temperature: number | null;
  battery: number | null;
  leftTarget: number | null;
  leftActual: number | null;
  rightTarget: number | null;
  rightActual: number | null;
  leftError: number | null;
  rightError: number | null;
  requestedLinear: number | null;
  limitedLinear: number | null;
  measuredLinear: number | null;
  requestedAngular: number | null;
  limitedAngular: number | null;
  measuredAngular: number | null;
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
export interface AutonomousSpeedLimits {
  max_linear: number;
  max_angular: number;
}
export interface WheelConstraints {
  max_rpm: number;
  acceleration_rpm_s: number;
}
export interface RobotConfiguration {
  version: 1;
  home: Goal;
  waypoints: Partial<Record<WaypointName, Goal>>;
  autonomous_speed_limits: AutonomousSpeedLimits;
  autonomous_speed_limit_ranges: Record<
    keyof AutonomousSpeedLimits,
    { min: number; max: number }
  >;
  wheel_constraints: WheelConstraints;
  wheel_constraint_ranges: Record<
    keyof WheelConstraints,
    { min: number; max: number }
  >;
  effective_wheel_constraints: WheelConstraints;
  kinematic_limits: {
    max_straight_linear: number;
    max_in_place_angular: number;
    max_straight_acceleration: number;
    max_in_place_angular_acceleration: number;
    effective_autonomous_speed_limits: AutonomousSpeedLimits;
  };
  storage: "local-file" | "memory";
  load_warnings: string[];
}
export interface HistoryRecord {
  timestamp: string;
  session_id: string;
  left_target_rpm?: number | null;
  left_actual_rpm?: number | null;
  right_target_rpm?: number | null;
  right_actual_rpm?: number | null;
  left_error_rpm?: number | null;
  right_error_rpm?: number | null;
  requested_linear?: number | null;
  limited_linear?: number | null;
  linear_velocity?: number | null;
  requested_angular?: number | null;
  limited_angular?: number | null;
  angular_velocity?: number | null;
  cpu_percent?: number | null;
  memory_percent?: number | null;
  temperature_c?: number | null;
  battery_percent?: number | null;
}
export type BodyVelocity = { linear: number; angular: number };
export interface Diagnostics {
  source: "simulation";
  model: string;
  motion: {
    requested: BodyVelocity;
    limited: BodyVelocity;
    measured: BodyVelocity;
    limit_active: boolean;
    autonomous_limit_active: boolean;
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
    autonomous_limits_blocked_reason: string | null;
  };
  counters: Record<string, number>;
  integration_status: {
    backend: "simulation";
    ros2_connected: false;
    nav2_connected: false;
    esp32_s3_connected: false;
  };
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
