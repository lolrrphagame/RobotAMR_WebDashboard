import type { Pose } from "./types";
export type SensorSource = "SIMULATED" | "PLACEHOLDER" | "DISABLED";
export type SensorStatus =
  "INITIALIZING" | "READY" | "NOT_CONNECTED" | "DISABLED" | "STALE" | "ERROR";
export interface SensorFrame<M, P> {
  sensor_type: "lidar_2d" | "camera";
  source: SensorSource;
  status: SensorStatus;
  timestamp: string | null;
  frame_id: string;
  sequence: number;
  error: string | null;
  freshness: { age_ms: number | null; stale: boolean; timeout_ms: number };
  metadata: M;
  interface: {
    connection_state: "DISABLED";
    planned_topic: string;
    compressed_topic?: string;
    message_types: string[];
    note: string;
  };
  payload?: P | null;
}
export interface LidarMetadata {
  beam_count: number;
  angle_min: number;
  angle_max: number;
  angle_increment: number;
  range_min: number;
  range_max: number;
  scan_time: number;
  time_increment: number;
  nominal_hz: number;
  min_obstacle_distance: number | null;
  hit_count: number;
  map_frame: string;
}
export interface LidarPayload {
  ranges: number[];
  hits: boolean[];
  acquisition_pose: Pose & { frame_id: string };
}
export interface CameraMetadata {
  width: number | null;
  height: number | null;
  encoding: string | null;
  fps: number | null;
  stream_url: string | null;
  preview_kind: string;
  frames_received: number;
}
export type LidarFrame = SensorFrame<LidarMetadata, LidarPayload>;
export type CameraFrame = SensorFrame<CameraMetadata, never>;
export interface SensorBundle {
  type: "sensors";
  simulation: true;
  session_id: string;
  lidar: LidarFrame;
  camera: CameraFrame;
}
export type SensorConnection =
  "idle" | "connecting" | "connected" | "disconnected";
export function scanAge(
  frame: LidarFrame | null | undefined,
  now: number,
): number | null {
  return frame?.timestamp
    ? Math.max(0, now - Date.parse(frame.timestamp))
    : null;
}
export function scanState(
  frame: LidarFrame | null | undefined,
  connection: SensorConnection,
  now: number,
): string {
  if (connection === "disconnected") return "DISCONNECTED";
  if (connection !== "connected" || !frame) return "WAITING";
  if (frame.status === "ERROR") return "ERROR";
  if (frame.status === "INITIALIZING" || frame.status === "DISABLED")
    return frame.status;
  const age = scanAge(frame, now);
  if (
    frame.status === "STALE" ||
    frame.freshness.stale ||
    (age !== null && age > frame.freshness.timeout_ms)
  )
    return "STALE";
  return frame.status;
}
export function laserWorldPoints(frame: LidarFrame): [number, number][] {
  const scan = frame.payload;
  if (!scan) return [];
  return scan.ranges.flatMap((range, i) => {
    if (!scan.hits[i]) return [];
    const angle =
      scan.acquisition_pose.yaw +
      frame.metadata.angle_min +
      i * frame.metadata.angle_increment;
    return [
      [
        scan.acquisition_pose.x + range * Math.cos(angle),
        scan.acquisition_pose.y + range * Math.sin(angle),
      ] as [number, number],
    ];
  });
}
export function validateSensorBundle(value: unknown): value is SensorBundle {
  if (!value || typeof value !== "object") return false;
  const message = value as SensorBundle;
  const frame = message.lidar;
  const camera = message.camera;
  if (
    message.type !== "sensors" ||
    message.simulation !== true ||
    typeof message.session_id !== "string" ||
    !frame ||
    !camera
  )
    return false;
  if (
    frame.source !== "SIMULATED" ||
    frame.sensor_type !== "lidar_2d" ||
    camera.sensor_type !== "camera" ||
    !["PLACEHOLDER", "DISABLED", "SIMULATED"].includes(camera.source)
  )
    return false;
  if (
    !camera.metadata ||
    !camera.interface ||
    !frame.interface ||
    typeof camera.frame_id !== "string" ||
    typeof frame.frame_id !== "string"
  )
    return false;
  if (
    !Number.isInteger(frame.sequence) ||
    frame.sequence < 0 ||
    !Number.isInteger(camera.sequence) ||
    camera.sequence < 0
  )
    return false;
  for (const sensor of [frame, camera]) {
    if (sensor.error !== null && typeof sensor.error !== "string") return false;
    if (
      sensor.timestamp !== null &&
      (typeof sensor.timestamp !== "string" ||
        !Number.isFinite(Date.parse(sensor.timestamp)))
    )
      return false;
    if (
      !sensor.freshness ||
      typeof sensor.freshness.stale !== "boolean" ||
      !Number.isFinite(sensor.freshness.timeout_ms) ||
      sensor.freshness.timeout_ms <= 0
    )
      return false;
  }
  const m = frame.metadata;
  if (
    !m ||
    !Number.isInteger(m.beam_count) ||
    m.beam_count < 2 ||
    m.beam_count > 361 ||
    !Number.isFinite(m.range_max) ||
    m.range_max <= 0 ||
    m.range_max > 20 ||
    typeof m.map_frame !== "string" ||
    !Number.isFinite(m.angle_max) ||
    !Number.isFinite(m.nominal_hz) ||
    m.nominal_hz <= 0 ||
    m.nominal_hz > 5 ||
    (m.min_obstacle_distance !== null &&
      (!Number.isFinite(m.min_obstacle_distance) ||
        m.min_obstacle_distance < 0 ||
        m.min_obstacle_distance > m.range_max)) ||
    !Number.isFinite(m.angle_min) ||
    !Number.isFinite(m.angle_increment) ||
    m.angle_increment <= 0
  )
    return false;
  if (
    !frame.freshness ||
    !Number.isFinite(frame.freshness.timeout_ms) ||
    !["READY", "STALE", "INITIALIZING", "ERROR", "DISABLED"].includes(
      frame.status,
    )
  )
    return false;
  if (frame.timestamp !== null && !Number.isFinite(Date.parse(frame.timestamp)))
    return false;
  if (frame.payload) {
    const p = frame.payload;
    if (
      !Array.isArray(p.ranges) ||
      !Array.isArray(p.hits) ||
      p.ranges.length !== m.beam_count ||
      p.hits.length !== m.beam_count ||
      !p.ranges.every(
        (r) => Number.isFinite(r) && r >= 0 && r <= m.range_max,
      ) ||
      !p.hits.every((h) => typeof h === "boolean") ||
      !p.acquisition_pose ||
      p.acquisition_pose.frame_id !== m.map_frame ||
      ![
        p.acquisition_pose.x,
        p.acquisition_pose.y,
        p.acquisition_pose.yaw,
      ].every(Number.isFinite)
    )
      return false;
  } else if (frame.status === "READY") return false;
  if (
    camera.source === "PLACEHOLDER" &&
    (!camera.metadata ||
      camera.timestamp !== null ||
      camera.metadata.fps !== null ||
      camera.metadata.width !== null ||
      camera.metadata.height !== null ||
      camera.metadata.stream_url !== null)
  )
    return false;
  return true;
}
