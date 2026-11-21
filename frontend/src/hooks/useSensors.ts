import { useEffect, useState } from "react";
import { refreshAuth } from "../auth";
import { validateSensorBundle, scanState } from "../sensors";
import type { SensorBundle, SensorConnection } from "../sensors";
export function useSensors(enabled: boolean) {
  const [bundle, setBundle] = useState<SensorBundle | null>(null);
  const [connection, setConnection] = useState<SensorConnection>("idle");
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!enabled) {
      setConnection("idle");
      return;
    }
    let disposed = false;
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout>;
    const connect = () => {
      if (disposed) return;
      setConnection("connecting");
      const ws = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/sensors`,
      );
      socket = ws;
      ws.onmessage = (event) => {
        if (disposed || socket !== ws) return;
        try {
          const message = JSON.parse(event.data) as unknown;
          if (!validateSensorBundle(message)) throw Error("invalid");
          setBundle(message);
          setConnection("connected");
          setError("");
          setNow(Date.now());
        } catch {
          setError(
            "Invalid simulated sensor payload. Retrying the read-only stream.",
          );
          ws.close();
        }
      };
      ws.onerror = () => {
        if (!disposed)
          setError(
            "Sensor stream unavailable. Robot control uses a separate connection.",
          );
      };
      ws.onclose = (event) => {
        if (!disposed) {
          if (event.code === 1008) {
            setBundle(null);
            void refreshAuth().catch(() => {});
          }
          setConnection("disconnected");
          retry = setTimeout(connect, 2000);
        }
      };
    };
    connect();
    const clock = setInterval(() => setNow(Date.now()), 250);
    return () => {
      disposed = true;
      clearTimeout(retry);
      clearInterval(clock);
      socket?.close();
    };
  }, [enabled]);
  return {
    bundle,
    connection,
    error,
    now,
    state: scanState(bundle?.lidar, connection, now),
  };
}
