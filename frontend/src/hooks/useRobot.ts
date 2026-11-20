import { useCallback, useEffect, useRef, useState } from "react";
import type { Command, Sample, Telemetry } from "../types";

export function useRobot() {
  const [data, setData] = useState<Telemetry | null>(null);
  const [history, setHistory] = useState<Sample[]>([]);
  const [connection, setConnection] = useState<
    "connecting" | "connected" | "disconnected"
  >("connecting");
  const [error, setError] = useState("");
  const socket = useRef<WebSocket | null>(null);
  const command = useRef<Command>({ type: "stop" });
  const send = useCallback((next: Command) => {
    if (
      next.type === "control" ||
      next.type === "stop" ||
      next.type === "release"
    )
      command.current = next;
    if (socket.current?.readyState === WebSocket.OPEN)
      socket.current.send(JSON.stringify(next));
  }, []);
  const stop = useCallback(() => send({ type: "stop" }), [send]);
  const release = useCallback(() => send({ type: "release" }), [send]);
  useEffect(() => {
    let disposed = false;
    let retry: ReturnType<typeof setTimeout>;
    let lastMessage = Date.now();
    const connect = () => {
      if (disposed) return;
      command.current = { type: "stop" };
      const ws = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/telemetry`,
      );
      socket.current = ws;
      ws.onopen = () => {
        lastMessage = Date.now();
        setError("");
      };
      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message.type === "ack") {
            setError("");
            return;
          }
          if (message.type === "error") {
            command.current = { type: "stop" };
            setError(message.message);
            return;
          }
          if (
            message.type !== "telemetry" ||
            message.simulation !== true ||
            !Array.isArray(message.motors) ||
            message.motors.length !== 2
          )
            throw Error("Unexpected telemetry");
          const next = message as Telemetry;
          lastMessage = Date.now();
          setConnection("connected");
          setData(next);
          setHistory((old) => [
            ...old.slice(-149),
            {
              time: new Date(next.timestamp).toLocaleTimeString(),
              leftTarget: next.motors[0].target_rpm,
              leftActual: next.motors[0].actual_rpm,
              rightTarget: next.motors[1].target_rpm,
              rightActual: next.motors[1].actual_rpm,
            },
          ]);
        } catch {
          setError("Invalid telemetry received. Reconnecting safely.");
          stop();
          ws.close();
        }
      };
      ws.onerror = () =>
        setError(
          "Telemetry service unavailable. Check that the backend is running.",
        );
      ws.onclose = () => {
        command.current = { type: "stop" };
        if (!disposed) {
          setConnection("disconnected");
          retry = setTimeout(connect, 2000);
        }
      };
    };
    connect();
    const heartbeat = setInterval(() => {
      if (socket.current?.readyState === WebSocket.OPEN) {
        if (Date.now() - lastMessage > 2000) {
          stop();
          socket.current.close();
          return;
        }
        socket.current.send(JSON.stringify({ type: "heartbeat" }));
        if (command.current.type === "control")
          socket.current.send(JSON.stringify(command.current));
      }
    }, 150);
    const hidden = () => {
      if (document.hidden) release();
    };
    window.addEventListener("blur", release);
    window.addEventListener("pagehide", release);
    document.addEventListener("visibilitychange", hidden);
    return () => {
      disposed = true;
      clearTimeout(retry);
      clearInterval(heartbeat);
      release();
      socket.current?.close();
      window.removeEventListener("blur", release);
      window.removeEventListener("pagehide", release);
      document.removeEventListener("visibilitychange", hidden);
    };
  }, [stop, release]);
  return { data, history, connection, error, send, stop, release };
}
