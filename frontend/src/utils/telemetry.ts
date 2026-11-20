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
export const formatTime = (value: string) => clock.format(new Date(value));
export const formatTimestamp = (value: string) =>
  `${date.format(new Date(value))} ${formatTime(value)} UTC+07`;
export function historyToSample(row: HistoryRecord): Sample {
  return {
    timestamp: row.timestamp,
    time: formatTime(row.timestamp),
    leftTarget: row.left_target_rpm,
    leftActual: row.left_actual_rpm,
    rightTarget: row.right_target_rpm,
    rightActual: row.right_actual_rpm,
    cpu: row.cpu_percent,
    ram: row.memory_percent,
    temperature: row.temperature_c,
    battery: row.battery_percent,
  };
}
export function frameToSample(frame: Telemetry): Sample {
  return historyToSample({
    timestamp: frame.timestamp,
    left_target_rpm: frame.motors[0].target_rpm,
    left_actual_rpm: frame.motors[0].actual_rpm,
    right_target_rpm: frame.motors[1].target_rpm,
    right_actual_rpm: frame.motors[1].actual_rpm,
    ...frame.health,
  });
}
export function mergeHistory(old: Sample[], incoming: Sample[]): Sample[] {
  return [
    ...new Map(
      [...old, ...incoming].map((row) => [row.timestamp, row]),
    ).values(),
  ]
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
    .slice(-600);
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
