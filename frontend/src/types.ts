export interface Telemetry {
  type: "telemetry";
  simulation: true;
  timestamp: string;
  mode: string;
  uptime: number;
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
export type Command = {
  type: "control" | "stop";
  linear?: number;
  angular?: number;
};
