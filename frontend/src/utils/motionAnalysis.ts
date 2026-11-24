import type { Sample } from "../types";

export function trackingStats(
  history: Sample[],
  error: (sample: Sample) => number | null,
) {
  let count = 0;
  let absoluteSum = 0;
  let squareSum = 0;
  let max = 0;
  for (const sample of history) {
    const value = error(sample);
    if (value === null || !Number.isFinite(value)) continue;
    const absolute = Math.abs(value);
    count++;
    absoluteSum += absolute;
    squareSum += value * value;
    max = Math.max(max, absolute);
  }
  return count
    ? {
        count,
        mae: absoluteSum / count,
        rmse: Math.sqrt(squareSum / count),
        max,
      }
    : null;
}

export function bodyTrackingError(
  limited: number | null,
  measured: number | null,
) {
  return limited === null || measured === null ? null : limited - measured;
}
