import { CameraOff } from "lucide-react";
import type { CameraFrame } from "../../sensors";
import { formatTimestamp } from "../../utils/telemetry";
export function CameraMonitor({ frame }: { frame: CameraFrame | null }) {
  const canPreview =
    frame?.status === "READY" &&
    frame.source !== "PLACEHOLDER" &&
    frame.metadata.stream_url?.startsWith("/api/");
  return (
    <section className="panel camera-monitor">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">FRONT / OPTICAL FRAME</span>
          <h2>Front Camera Monitor</h2>
        </div>
        <span className="sensor-source placeholder">
          {frame?.source ?? "PLACEHOLDER"}
        </span>
      </div>
      {frame?.error && (
        <p role="alert" className="connection-alert">
          {frame.error}
        </p>
      )}
      <div className="camera-preview" data-testid="camera-preview">
        {canPreview ? (
          <img
            src={frame.metadata.stream_url!}
            alt="Adapter-provided, explicitly sourced camera frames"
          />
        ) : (
          <>
            <div className="camera-test-pattern" aria-hidden="true" />
            <div className="camera-placeholder">
              <CameraOff size={35} />
              <strong>NOT CONNECTED</strong>
              <span>STATIC TEST PATTERN · NO CAMERA FRAMES</span>
              <p>This preview is a UI placeholder, not a live camera feed.</p>
            </div>
          </>
        )}
      </div>
      <dl className="sensor-details">
        <div>
          <dt>Camera status</dt>
          <dd>{frame?.status ?? "NOT_CONNECTED"}</dd>
        </div>
        <div>
          <dt>Data source</dt>
          <dd>{frame?.source ?? "PLACEHOLDER"}</dd>
        </div>
        <div>
          <dt>Frame resolution</dt>
          <dd>
            {frame?.metadata.width && frame.metadata.height
              ? `${frame.metadata.width} × ${frame.metadata.height}`
              : "Unavailable"}
          </dd>
        </div>
        <div>
          <dt>Latest frame</dt>
          <dd>
            {frame?.timestamp
              ? formatTimestamp(frame.timestamp)
              : "Unavailable · no frames"}
          </dd>
        </div>
        <div>
          <dt>Frame rate</dt>
          <dd>
            {frame?.metadata.fps != null
              ? `${frame.metadata.fps} FPS`
              : "Unavailable"}
          </dd>
        </div>
        <div>
          <dt>Frame ID</dt>
          <dd>{frame?.frame_id ?? "front_camera_optical"}</dd>
        </div>
        <div>
          <dt>Data freshness</dt>
          <dd>
            {frame?.timestamp
              ? frame.freshness.stale
                ? "Stale"
                : "Current"
              : "Unavailable · no frames"}
          </dd>
        </div>
      </dl>
      <div className="sensor-interface">
        <span className="eyebrow">FUTURE BACKEND STREAMING ADAPTER</span>
        <p>
          /camera/image_raw · sensor_msgs/Image
          <br />
          /camera/image_raw/compressed · sensor_msgs/CompressedImage
        </p>
        <span className="tag">ROS 2 DISABLED</span>
      </div>
    </section>
  );
}
