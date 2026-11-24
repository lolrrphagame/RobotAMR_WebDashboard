import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Square,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Command, MotionAuthority } from "../types";
export function ManualControl({
  connected,
  authority,
  readOnly = false,
  send,
  stop,
  release: releaseInput,
}: {
  connected: boolean;
  authority?: MotionAuthority;
  readOnly?: boolean;
  send: (c: Command) => void;
  stop: () => void;
  release: () => void;
}) {
  const [linear, setLinear] = useState(0.12);
  const [angular, setAngular] = useState(0.6);
  const [active, setActive] = useState("");
  const held = useRef(false);
  const canDrive = connected && !readOnly && authority !== "AUTONOMOUS";
  const release = () => {
    held.current = false;
    setActive("");
    releaseInput();
  };
  useEffect(() => {
    if (!canDrive && held.current) {
      held.current = false;
      setActive("");
      releaseInput();
    }
  }, [canDrive, releaseInput]);
  useEffect(() => {
    const halt = () => {
      if (!held.current) return;
      held.current = false;
      setActive("");
      releaseInput();
    };
    const key = (event: KeyboardEvent) => {
      if (
        event.code === "Space" &&
        !(event.target instanceof HTMLInputElement) &&
        !(event.target instanceof HTMLButtonElement)
      ) {
        event.preventDefault();
        halt();
        stop();
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
      releaseInput();
    };
  }, [stop, releaseInput]);
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
      <p className="muted">
        Press and hold a direction. Release to stop. Speed sliders apply to
        manual driving.
      </p>
      <div className="dpad">
        {buttons.map(({ id, label, Icon, v, w }) => (
          <button
            key={id}
            className={`drive ${id} ${active === id ? "active" : ""}`}
            aria-label={label}
            disabled={!canDrive}
            onContextMenu={(e) => e.preventDefault()}
            onPointerDown={(e) => {
              if (e.button !== 0) return;
              e.preventDefault();
              e.currentTarget.setPointerCapture(e.pointerId);
              held.current = true;
              setActive(id);
              send({ type: "control", linear: v, angular: w });
            }}
            onPointerUp={release}
            onPointerCancel={release}
            onLostPointerCapture={release}
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === " ") && !e.repeat) {
                e.preventDefault();
                held.current = true;
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
          disabled={!connected || readOnly}
          onClick={() => {
            release();
            stop();
          }}
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
        min="0.02"
        max="0.18"
        step="0.01"
        value={linear}
        disabled={!canDrive}
        onChange={(e) => {
          release();
          setLinear(Number(e.target.value));
        }}
      />
      <div className="range-ticks">
        <span>0.02 m/s</span>
        <span>0.18 m/s</span>
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
        max="1.2"
        step="0.1"
        value={angular}
        disabled={!canDrive}
        onChange={(e) => {
          release();
          setAngular(Number(e.target.value));
        }}
      />
      <div className="range-ticks">
        <span>0.2 rad/s</span>
        <span>1.2 rad/s</span>
      </div>
      <div className="safety-note">
        <span className="status-dot" />
        40 RPM wheel limit · simulation only
      </div>
    </section>
  );
}
