import { useState, type FormEvent } from "react";
import type {
  AutonomousSpeedLimits,
  Telemetry,
  WheelConstraints,
} from "../types";

type MotionValues = AutonomousSpeedLimits & WheelConstraints;
const autonomousFields = [
  { key: "max_linear", label: "Maximum linear speed", unit: "m/s" },
  { key: "max_angular", label: "Maximum angular speed", unit: "rad/s" },
] as const;
const wheelFields = [
  { key: "max_rpm", label: "Maximum wheel speed", unit: "RPM" },
  { key: "acceleration_rpm_s", label: "Wheel acceleration", unit: "RPM/s" },
] as const;

export function MotionSettings({
  data,
  operator,
}: {
  data: Telemetry | null;
  operator: boolean;
}) {
  const [draft, setDraft] = useState<
    Partial<Record<keyof MotionValues, string>>
  >({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const config = data?.configuration;
  const drive = data?.drive;
  const limits = config?.kinematic_limits;
  const saved = config && {
    ...config.autonomous_speed_limits,
    ...config.wheel_constraints,
  };
  const ranges = config && {
    ...config.autonomous_speed_limit_ranges,
    ...config.wheel_constraint_ranges,
  };
  const blockedReason =
    !operator && data
      ? "Observer access is read-only. An Operator can save motion settings."
      : !data
        ? "Connect to the simulator to edit motion settings."
        : data.diagnostics.safety.autonomous_limits_blocked_reason;
  const fieldChanged = ({ key }: { key: keyof MotionValues }) =>
    saved && key in draft && Number(draft[key]) !== saved[key];
  const autonomousChanged = autonomousFields.some(fieldChanged);
  const wheelChanged = wheelFields.some(fieldChanged);
  const changed = autonomousChanged || wheelChanged;
  const updateDraft = (key: keyof MotionValues, value: string) => {
    setDraft((old) => ({ ...old, [key]: value }));
    setError("");
    setStatus("");
  };

  async function saveMotion(restore: boolean) {
    if (!saved || blockedReason || saving || (!restore && !changed)) return;
    const update = {
      type: "configuration",
      action: "set_motion_settings",
      autonomous_speed_limits: autonomousChanged
        ? {
            max_linear: Number(draft.max_linear ?? saved.max_linear),
            max_angular: Number(draft.max_angular ?? saved.max_angular),
          }
        : undefined,
      wheel_constraints: wheelChanged
        ? {
            max_rpm: Number(draft.max_rpm ?? saved.max_rpm),
            acceleration_rpm_s: Number(
              draft.acceleration_rpm_s ?? saved.acceleration_rpm_s,
            ),
          }
        : undefined,
    };
    setSaving(true);
    setError("");
    setStatus("");
    try {
      const response = await fetch("/api/configuration", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          restore
            ? { type: "configuration", action: "restore_motion_defaults" }
            : update,
        ),
      });
      if (!response.ok) {
        const { detail } = await response.json();
        throw Error(
          typeof detail === "string"
            ? detail
            : "Enter values within the displayed simulation ranges.",
        );
      }
      setDraft({});
      setStatus(
        restore ? "Motion defaults restored." : "Motion settings saved.",
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not save motion settings.",
      );
    } finally {
      setSaving(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void saveMotion(false);
  }

  return (
    <section
      className="panel motion-settings"
      aria-labelledby="motion-settings-title"
    >
      <div className="panel-heading">
        <h2 id="motion-settings-title">Motion Control &amp; Speed Limits</h2>
      </div>
      <div className="motion-settings-body">
        <div className="motion-authority">
          <span>Current control authority</span>
          <strong data-testid="settings-motion-authority">
            {data?.mode ?? "Unavailable"}
          </strong>
        </div>
        <form
          className="motion-limit-form"
          onSubmit={submit}
          aria-describedby="motion-limit-availability"
        >
          {[
            {
              title: "Autonomous speed caps",
              fields: autonomousFields,
              sliders: false,
            },
            {
              title: "Wheel constraints · Manual and Autonomous",
              fields: wheelFields,
              sliders: true,
            },
          ].map(({ title, fields, sliders }) => (
            <fieldset key={title} disabled={!!blockedReason || saving}>
              <legend>{title}</legend>
              <div className="goal-coordinates motion-limit-fields">
                {fields.map(({ key, label, unit }) => {
                  const value = draft[key] ?? saved?.[key] ?? "";
                  const range = ranges?.[key];
                  return (
                    <div key={key}>
                      <label htmlFor={`motion-limit-${key}`}>
                        {label} ({unit})
                      </label>
                      <input
                        id={`motion-limit-${key}`}
                        type="number"
                        step="any"
                        required
                        min={range?.min}
                        max={range?.max}
                        aria-describedby={`motion-range-${key}`}
                        value={value}
                        onChange={(event) =>
                          updateDraft(key, event.target.value)
                        }
                      />
                      {sliders && range && (
                        <input
                          className="motion-limit-slider"
                          type="range"
                          aria-label={`Adjust ${label.toLowerCase()}`}
                          aria-describedby={`motion-range-${key}`}
                          min={range.min}
                          max={range.max}
                          step="1"
                          value={value || saved?.[key]}
                          onChange={(event) =>
                            updateDraft(key, event.target.value)
                          }
                        />
                      )}
                      <span id={`motion-range-${key}`}>
                        {range && `Range ${range.min}–${range.max} ${unit}`}
                      </span>
                    </div>
                  );
                })}
              </div>
            </fieldset>
          ))}
          <div className="motion-settings-actions">
            <button
              className="primary-action"
              type="submit"
              disabled={!!blockedReason || saving || !changed}
            >
              {saving ? "Saving…" : "Save motion settings"}
            </button>
            <button
              className="secondary-button"
              type="button"
              disabled={!!blockedReason || saving}
              onClick={() => void saveMotion(true)}
            >
              Restore Motion Defaults
            </button>
          </div>
          <p className="muted" id="motion-limit-availability">
            {blockedReason ??
              "Save or restore while stationary with no held manual input or active mission reservation."}
          </p>
          {error && (
            <p className="motion-limit-error" role="alert">
              {error}
            </p>
          )}
          {status && (
            <p className="muted" role="status">
              {status}
            </p>
          )}
        </form>
        <section
          className="motion-constraints"
          aria-labelledby="kinematic-limits-title"
        >
          <h3 id="kinematic-limits-title">Effective simulation limits</h3>
          <div className="diagnostic-table-wrap">
            <table
              className="diagnostic-table"
              aria-label="Configured and effective limits"
            >
              <thead>
                <tr>
                  <th>Limit</th>
                  <th>Configured</th>
                  <th>Effective</th>
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    [
                      "Autonomous linear speed",
                      saved?.max_linear,
                      limits?.effective_autonomous_speed_limits.max_linear,
                      "m/s",
                      4,
                    ],
                    [
                      "Autonomous angular speed",
                      saved?.max_angular,
                      limits?.effective_autonomous_speed_limits.max_angular,
                      "rad/s",
                      4,
                    ],
                    ["Wheel speed", saved?.max_rpm, drive?.max_rpm, "RPM", 2],
                    [
                      "Wheel acceleration",
                      saved?.acceleration_rpm_s,
                      drive?.acceleration_rpm_s,
                      "RPM/s",
                      2,
                    ],
                  ] as const
                ).map(([label, configured, effective, unit, precision]) => (
                  <tr key={label}>
                    <th scope="row">{label}</th>
                    {[configured, effective].map((value, index) => (
                      <td key={index}>
                        {value === undefined
                          ? "—"
                          : `${Number(value.toFixed(precision))} ${unit}`}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <dl className="detail-grid">
            {[
              [
                "Maximum straight-line velocity",
                limits && `${limits.max_straight_linear.toFixed(4)} m/s`,
              ],
              [
                "Maximum in-place angular velocity",
                limits && `${limits.max_in_place_angular.toFixed(4)} rad/s`,
              ],
              [
                "Straight-line acceleration",
                limits && `${limits.max_straight_acceleration.toFixed(4)} m/s²`,
              ],
              [
                "In-place angular acceleration",
                limits &&
                  `${limits.max_in_place_angular_acceleration.toFixed(4)} rad/s²`,
              ],
              ["Wheel radius", drive && `${drive.wheel_radius.toFixed(4)} m`],
              [
                "Wheel separation",
                drive && `${drive.wheel_separation.toFixed(3)} m`,
              ],
              [
                "Encoder resolution",
                drive && `${drive.encoder_cpr.toLocaleString()} counts/rev`,
              ],
              [
                "Chassis",
                drive &&
                  `${drive.chassis_size * 1000} × ${drive.chassis_size * 1000} mm · two wheels + caster`,
              ],
              [
                "Footprint clearance",
                data && `${data.clearance.radius.toFixed(3)} m`,
              ],
            ].map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>
                  <strong>{value ?? "—"}</strong>
                </dd>
              </div>
            ))}
          </dl>
          <p className="muted">
            Straight-line and in-place maxima describe separate envelopes.
            Combined linear and angular commands share the same per-wheel limit
            and scale together when a wheel would exceed it. These ranges and
            calculations describe the simulator only.
          </p>
        </section>
      </div>
    </section>
  );
}
