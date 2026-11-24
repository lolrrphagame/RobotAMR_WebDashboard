import { useState, type FormEvent } from "react";
import type { AutonomousSpeedLimits, Telemetry } from "../types";

const limitFields = [
  { key: "max_linear", label: "Maximum linear speed", unit: "m/s" },
  { key: "max_angular", label: "Maximum angular speed", unit: "rad/s" },
] as const;

export function MotionSettings({
  data,
  operator,
}: {
  data: Telemetry | null;
  operator: boolean;
}) {
  const [draft, setDraft] = useState<
    Partial<Record<keyof AutonomousSpeedLimits, string>>
  >({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const saved = data?.configuration.autonomous_speed_limits;
  const ranges = data?.configuration.autonomous_speed_limit_ranges;
  const drive = data?.drive;
  const blockedReason = !data
    ? "Connect to the simulator to edit speed limits."
    : !operator
      ? "Observer access is read-only. An Operator can save speed limits."
      : data.diagnostics.safety.autonomous_limits_blocked_reason;
  const changed =
    saved &&
    limitFields.some(
      ({ key }) => key in draft && Number(draft[key]) !== saved[key],
    );

  async function saveLimits(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!saved || !changed || blockedReason || saving) return;
    const limits: AutonomousSpeedLimits = {
      max_linear: Number(draft.max_linear ?? saved.max_linear),
      max_angular: Number(draft.max_angular ?? saved.max_angular),
    };
    setSaving(true);
    setError("");
    setStatus("");
    try {
      const response = await fetch("/api/configuration", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: "configuration",
          action: "set_autonomous_speed_limits",
          autonomous_speed_limits: limits,
        }),
      });
      if (!response.ok) {
        const { detail } = await response.json();
        throw Error(
          typeof detail === "string"
            ? detail
            : "Enter both speed limits within the displayed simulation ranges.",
        );
      }
      setDraft({});
      setStatus("Autonomous speed limits saved.");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not save speed limits.",
      );
    } finally {
      setSaving(false);
    }
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
        <p className="muted">
          Standby means no motion owner. Manual Control uses hold-to-drive
          directions and its own speed sliders. Starting Navigation or a Mission
          Operations run assigns autonomous authority.
        </p>
        <form className="motion-limit-form" onSubmit={saveLimits}>
          <fieldset
            disabled={!!blockedReason || saving}
            aria-describedby="motion-limit-availability"
          >
            <legend>Autonomous Speed Limits</legend>
            <p className="muted">
              The simulated controller calculates each velocity request. These
              caps scale autonomous commands together to preserve path
              curvature.
            </p>
            <div className="goal-coordinates motion-limit-fields">
              {limitFields.map(({ key, label, unit }) => (
                <div key={key}>
                  <label htmlFor={`motion-limit-${key}`}>
                    {label} ({unit})
                  </label>
                  <input
                    id={`motion-limit-${key}`}
                    type="number"
                    step="any"
                    required
                    min={ranges?.[key].min}
                    max={ranges?.[key].max}
                    aria-describedby={`motion-range-${key}`}
                    value={draft[key] ?? saved?.[key] ?? ""}
                    onChange={(event) => {
                      setDraft({ ...draft, [key]: event.target.value });
                      setError("");
                      setStatus("");
                    }}
                  />
                  <span id={`motion-range-${key}`}>
                    {ranges &&
                      `Range ${ranges[key].min}–${ranges[key].max} ${unit}`}
                  </span>
                </div>
              ))}
            </div>
            <button
              className="primary-action"
              type="submit"
              disabled={!changed}
            >
              {saving ? "Saving…" : "Save autonomous limits"}
            </button>
          </fieldset>
          <p className="muted" id="motion-limit-availability">
            {blockedReason ?? "Save while stationary with no active mission."}
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
        <div className="motion-constraints">
          <h3>Simulated drive constraints</h3>
          <dl className="detail-grid">
            {[
              ["Wheel speed cap", drive && `${drive.max_rpm} RPM per wheel`],
              ["Wheel radius", drive && `${drive.wheel_radius.toFixed(4)} m`],
              [
                "Wheel separation",
                drive && `${drive.wheel_separation.toFixed(3)} m`,
              ],
              [
                "Wheel acceleration",
                drive && `${drive.acceleration_rpm_s} RPM/s`,
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
            The wheel RPM cap still applies to combined linear and angular
            motion. Navigation uses the local simulator. Nav2 is disconnected.
          </p>
        </div>
      </div>
    </section>
  );
}
