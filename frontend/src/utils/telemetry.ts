import type { HistoryRecord, Sample, Telemetry } from "../types";
const clock = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Ho_Chi_Minh",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});
const date = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Ho_Chi_Minh",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
export const formatTime = (value: string | number) =>
  clock.format(new Date(value));
export const formatTimestamp = (value: string) =>
  `${date.format(new Date(value))} ${formatTime(value)} UTC+07`;
const finite = (value?: number | null) =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

export function historyToSample(row: HistoryRecord): Sample {
  const epochMs = Date.parse(row.timestamp);
  return {
    timestamp: row.timestamp,
    sessionId: row.session_id,
    epochMs,
    time: Number.isFinite(epochMs) ? formatTime(epochMs) : "",
    leftTarget: finite(row.left_target_rpm),
    leftActual: finite(row.left_actual_rpm),
    rightTarget: finite(row.right_target_rpm),
    rightActual: finite(row.right_actual_rpm),
    leftError: finite(row.left_error_rpm),
    rightError: finite(row.right_error_rpm),
    requestedLinear: finite(row.requested_linear),
    limitedLinear: finite(row.limited_linear),
    measuredLinear: finite(row.linear_velocity),
    requestedAngular: finite(row.requested_angular),
    limitedAngular: finite(row.limited_angular),
    measuredAngular: finite(row.angular_velocity),
    cpu: finite(row.cpu_percent),
    ram: finite(row.memory_percent),
    temperature: finite(row.temperature_c),
    battery: finite(row.battery_percent),
  };
}
export function frameToSample(frame: Telemetry): Sample {
  const motion = frame.diagnostics.motion;
  return historyToSample({
    timestamp: frame.timestamp,
    session_id: frame.session_id,
    left_target_rpm: frame.motors[0].target_rpm,
    left_actual_rpm: frame.motors[0].actual_rpm,
    right_target_rpm: frame.motors[1].target_rpm,
    right_actual_rpm: frame.motors[1].actual_rpm,
    left_error_rpm: frame.motors[0].tracking_error_rpm,
    right_error_rpm: frame.motors[1].tracking_error_rpm,
    requested_linear: motion?.requested?.linear,
    requested_angular: motion?.requested?.angular,
    limited_linear: motion?.limited?.linear,
    limited_angular: motion?.limited?.angular,
    linear_velocity: frame.linear_velocity,
    angular_velocity: frame.angular_velocity,
    ...frame.health,
  });
}
export function mergeHistory(samples: Sample[], sessionId: string): Sample[] {
  const byTimestamp = new Map<string, Sample>();
  for (const row of samples) {
    if (row.sessionId === sessionId && Number.isFinite(row.epochMs))
      byTimestamp.set(row.timestamp, row);
  }
  return [...byTimestamp.values()]
    .sort(
      (a, b) => a.epochMs - b.epochMs || a.timestamp.localeCompare(b.timestamp),
    )
    .slice(-600);
}

export function historyWindow(history: Sample[], seconds: number) {
  const latest = history.at(-1);
  if (!latest) return [];
  const start = latest.epochMs - seconds * 1000;
  return history.filter(
    (row) => row.sessionId === latest.sessionId && row.epochMs >= start,
  );
}

export function withHistoryGaps(history: Sample[]) {
  const rows: (Partial<Sample> & Pick<Sample, "epochMs" | "time">)[] = [];
  let previous: Sample | undefined;
  for (const sample of history) {
    // The backend publishes at 10 Hz. Allow ordinary jitter between samples.
    if (
      previous &&
      (sample.sessionId !== previous.sessionId ||
        sample.epochMs - previous.epochMs > 175)
    ) {
      const epochMs = (previous.epochMs + sample.epochMs) / 2;
      rows.push({ epochMs, time: formatTime(epochMs) });
    }
    rows.push(sample);
    previous = sample;
  }
  return rows;
}
export async function downloadCsv(url: string, filename: string) {
  const response = await fetch(url);
  if (!response.ok)
    throw Error(
      `Export failed (${response.status}). Check the backend connection.`,
    );
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
