import { refreshAuth } from "../auth";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  frameToSample,
  historyToSample,
  mergeHistory,
} from "../utils/telemetry";
import type { HistoryRecord, Command, Sample, Telemetry } from "../types";

export function useRobot() {
  const [data, setData] = useState<Telemetry | null>(null);
  const [history, setHistory] = useState<Sample[]>([]);
  const [connection, setConnection] = useState<
    "connecting" | "connected" | "disconnected"
  >("connecting");
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [operator, setOperator] = useState(false);
  const authorized = useRef(false);
  const stopGeneration = useRef<number | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const session = useRef<string | null>(null);
  const command = useRef<Command>({ type: "stop" });
  const send = useCallback((next: Command) => {
    if (!authorized.current) return;
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
    const connect = async () => {
      if (disposed) return;
      try {
        const auth = await refreshAuth();
        if (disposed) return;
        authorized.current = auth.role === "operator";
        setOperator(authorized.current);
      } catch {
        if (!disposed) {
          setConnection("disconnected");
          retry = setTimeout(connect, 2000);
        }
        return;
      }
      command.current = { type: "stop" };
      const ws = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/telemetry`,
      );
      socket.current = ws;
      ws.onopen = () => {
        lastMessage = Date.now();
        setError("");
        fetch("/api/diagnostics/history")
          .then(async (response) => {
            if (!response.ok)
              throw Error(
                "Historical data unavailable; showing samples received in this browser.",
              );
            const body = (await response.json()) as {
              samples: HistoryRecord[];
              session_id: string;
            };
            if (
              !disposed &&
              socket.current === ws &&
              ws.readyState === WebSocket.OPEN
            ) {
              const changed =
                session.current !== null && session.current !== body.session_id;
              session.current = body.session_id;
              setHistory((old) =>
                mergeHistory(
                  changed ? [] : old,
                  body.samples.map(historyToSample),
                ),
              );
              setHistoryError("");
            }
          })
          .catch(() => {
            if (!disposed)
              setHistoryError(
                "Historical data unavailable; showing samples received in this browser.",
              );
          });
      };
      ws.onmessage = (event) => {
        if (disposed || socket.current !== ws) return;
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
          const generation = next.diagnostics.safety.stop_generation ?? 0;
          if (
            stopGeneration.current !== null &&
            stopGeneration.current !== generation
          )
            command.current = { type: "stop" };
          stopGeneration.current = generation;
          lastMessage = Date.now();
          setConnection("connected");
          setData(next);
          const changed =
            session.current !== null && session.current !== next.session_id;
          session.current = next.session_id;
          setHistory((old) =>
            mergeHistory(changed ? [] : old, [frameToSample(next)]),
          );
        } catch {
          setError("Invalid telemetry received. Reconnecting safely.");
          stop();
          ws.close();
        }
      };
      ws.onerror = () => {
        if (disposed || socket.current !== ws) return;
        setError(
          "Telemetry service unavailable. Check that the backend is running.",
        );
      };
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
        if (!authorized.current) return;
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
  return {
    operator,
    data,
    history,
    connection,
    error,
    historyError,
    send,
    stop,
    release,
  };
}
