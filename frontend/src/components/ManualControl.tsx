import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Square,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { Command } from "../types";
export function ManualControl({
  connected,
  send,
  stop,
}: {
  connected: boolean;
  send: (c: Command) => void;
  stop: () => void;
}) {
  const [linear, setLinear] = useState(0.25);
  const [angular, setAngular] = useState(0.8);
  const [active, setActive] = useState("");
  const release = () => {
    setActive("");
    stop();
  };
  useEffect(() => {
    if (!connected) setActive("");
  }, [connected]);
  useEffect(() => {
    const halt = () => {
      setActive("");
      stop();
    };
    const key = (event: KeyboardEvent) => {
      if (
        event.code === "Space" &&
        !(event.target instanceof HTMLInputElement) &&
        !(event.target instanceof HTMLButtonElement)
      ) {
        event.preventDefault();
        halt();
      }
    };
    window.addEventListener("pointerup", halt);
    window.addEventListener("pointercancel", halt);
    window.addEventListener("blur", halt);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("pointerup", halt);
      window.removeEventListener("pointercancel", halt);
      window.removeEventListener("blur", halt);
      window.removeEventListener("keydown", key);
      stop();
    };
  }, [stop]);
  const buttons = [
    { id: "forward", label: "Forward", Icon: ArrowUp, v: linear, w: 0 },
    { id: "left", label: "Rotate left", Icon: ArrowLeft, v: 0, w: angular },
    { id: "right", label: "Rotate right", Icon: ArrowRight, v: 0, w: -angular },
    { id: "backward", label: "Backward", Icon: ArrowDown, v: -linear, w: 0 },
  ];
  return (
    <section className="panel control-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">SIMULATED TELEOPERATION</span>
          <h2>Manual control</h2>
        </div>
        <span className="tag">HOLD TO DRIVE</span>
      </div>
      <p className="muted">Press and hold a direction. Release to stop.</p>
      <div className="dpad">
        {buttons.map(({ id, label, Icon, v, w }) => (
          <button
            key={id}
            className={`drive ${id} ${active === id ? "active" : ""}`}
            aria-label={label}
            disabled={!connected}
            onContextMenu={(e) => e.preventDefault()}
            onPointerDown={(e) => {
              if (e.button !== 0) return;
              e.preventDefault();
              e.currentTarget.setPointerCapture(e.pointerId);
              setActive(id);
              send({ type: "control", linear: v, angular: w });
            }}
            onPointerUp={release}
            onPointerCancel={release}
            onLostPointerCapture={release}
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === " ") && !e.repeat) {
                e.preventDefault();
                setActive(id);
                send({ type: "control", linear: v, angular: w });
              }
            }}
            onKeyUp={release}
            onBlur={release}
          >
            <Icon size={24} />
          </button>
        ))}
        <button
          className="stop"
          onClick={release}
          aria-label="Stop simulated robot"
        >
          <Square size={16} fill="currentColor" />
          STOP
        </button>
      </div>
      <label className="slider-label" htmlFor="linear">
        Linear speed{" "}
        <strong>
          {linear.toFixed(2)} <small>m/s</small>
        </strong>
      </label>
      <input
        id="linear"
        type="range"
        min="0.05"
        max="0.6"
        step="0.05"
        value={linear}
        onChange={(e) => {
          release();
          setLinear(Number(e.target.value));
        }}
      />
      <div className="range-ticks">
        <span>0.05 m/s</span>
        <span>0.60 m/s</span>
      </div>
      <label className="slider-label" htmlFor="angular">
        Angular speed{" "}
        <strong>
          {angular.toFixed(1)} <small>rad/s</small>
        </strong>
      </label>
      <input
        id="angular"
        type="range"
        min="0.2"
        max="2"
        step="0.1"
        value={angular}
        onChange={(e) => {
          release();
          setAngular(Number(e.target.value));
        }}
      />
      <div className="range-ticks">
        <span>0.2 rad/s</span>
        <span>2.0 rad/s</span>
      </div>
      <div className="safety-note">
        <span className="status-dot" />
        600 ms command watchdog · simulation only
      </div>
    </section>
  );
}
