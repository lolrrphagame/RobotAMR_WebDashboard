# PBL4 AMR Mission Control — Phase 4A

A simulation-only industrial robot dashboard built with React, TypeScript, Vite, Tailwind CSS, Recharts and FastAPI. No ROS, serial, GPIO, camera or motor interfaces are imported or opened. All controls, encoder readings and health values are simulated.

## Requirements

Ubuntu with **Node.js 24**, npm, and **Python 3.10+** with `venv` support. No system packages or `sudo` are needed by this project. If `python3 -m venv` is unavailable, ask your system administrator to provide venv support before continuing.

Your existing Node installation is managed by nvm. In a new terminal, load it if necessary:

```bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm use 24
node --version
python3 --version
```

## Install project-local dependencies

```bash
cd ~/Projects/PBL4_Dashboard
python3 -m venv backend/.venv
env -u PYTHONPATH backend/.venv/bin/python -m pip install -r backend/requirements.lock.txt
cd frontend
npm ci
```

`backend/requirements.txt` lists direct dependencies; `requirements.lock.txt` captures the tested Python 3.10 Ubuntu environment. `frontend/package-lock.json` locks JavaScript dependencies. The Python commands unset inherited `PYTHONPATH` because a ROS-enabled shell may otherwise inject ROS packages into the virtual environment. This does not modify your ROS installation.

## Run (two terminals)

Terminal 1 — backend:

```bash
cd ~/Projects/PBL4_Dashboard/backend
env -u PYTHONPATH .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 — frontend (load nvm as above if needed):

```bash
cd ~/Projects/PBL4_Dashboard/frontend
npm run dev -- --port 5173 --strictPort
```

Open **http://127.0.0.1:5173**. API documentation is at **http://127.0.0.1:8000/docs**. Stop each server with `Ctrl+C`. Use one backend worker: live motion, missions, counters, logs and history reset on restart. Saved Home and waypoints persist separately; a new session starts stationary at its validated saved Home.

The Vite development and preview servers proxy `/api` and `/ws` to port 8000. There is no separate browser API URL to configure. Keep both servers running. A disconnected dashboard automatically reconnects every two seconds, hides stale values, and never resumes a previous drive command.

## Build and verify

```bash
cd ~/Projects/PBL4_Dashboard
(cd backend && env -u PYTHONPATH .venv/bin/python -m pytest tests -q)
cd frontend
npm run build
```

To view the production bundle while the backend is running:

```bash
npm run preview -- --port 4173 --strictPort
```

Open **http://127.0.0.1:4173**. This is a local production-build preview, not a deployment setup.

Optional real-browser integration tests (downloads Chromium into project-local `node_modules`; no system installation):

```bash
cd ~/Projects/PBL4_Dashboard/frontend
PLAYWRIGHT_BROWSERS_PATH=0 npx playwright install chromium
npm run test:e2e
```

Browser tests start isolated frontend/backend servers on ports **15173 and 18000**, so your normal dev servers can remain running. These test ports must be available. Tests cover telemetry, pointer/keyboard release, focus loss, disconnect/reconnect, mobile overflow, map goal selection, heading, waypoint save, path planning, pause/resume, STOP, return home, invalid goals, command arbitration and matching poses across pages. If Chromium reports missing OS libraries, have your administrator supply them; do not use `install --with-deps` without approval.

## Dashboard

- **Overview:** authoritative map pose, heading, operating mode, mission status/progress, linear/angular velocity, both wheel RPMs, two target/actual RPM charts, encoder counts, system health and event stream.
- **Manual Control:** the same telemetry and hold-to-drive controls. Hold a directional button using mouse/touch or focus it and hold Enter/Space. Releasing stops the simulated robot. Use STOP at any time. Space outside buttons and input controls also stops.
- **Navigation:** interactive SVG occupancy map, virtual AMR with two powered wheels and a caster, heading, coordinate grid, planned path, trajectory, goal/heading selection, zoom/pan/reset, mission controls, A/B/C waypoint management and mission events.
- **Sensors:** a deterministic virtual LiDAR radar view and a clearly labeled, disconnected camera placeholder. Navigation offers an optional simulated laser-point overlay.
- **Diagnostics:** Motors, System Health, Communication and Events tabs with simulated measurements, bounded history, honest unavailable hardware fields, filtering and CSV exports.
- **Settings:** saved Home controls and read-only robot geometry/simulation parameters. Home can also be configured directly from Navigation.

Charts retain the most recent 150 samples (approximately 15 seconds at 10 Hz). The virtual robot starts stationary at its validated saved Home (default **1.0 m, 1.0 m, 0 rad**); hold a direction to see target and actual RPM responses. Wheel response uses a **60 RPM/s slew limit** for smooth acceleration, deceleration and reversal. Both target and actual speeds stay within **±40 RPM**. This is a kinematic model, not a firmware PI implementation or a measured hardware model. Health values are synthetic. Event history is bounded to 60 entries and is not persisted.

## Navigate the virtual AMR

1. Open **Navigation**. Click free space on the map, or enter X/Y coordinates. Occupied cells are blue-gray; dark cells are free space.
2. Choose a final heading with the slider. Alternatively select the map's **Heading** tool and click toward the desired heading from the goal marker. World +x is 0°, +y is 90°, and positive yaw turns counterclockwise.
3. Choose **Plan path** to preview A*, then **Start navigation** to plan from the current actual pose and move. Starting also works without a preview.
4. **Pause** holds the robot still and retains the mission. **Resume** replans unfinished legs and continues. **Cancel mission** and **STOP** immediately zero motion, clear the live route/destination/progress (including a blocked mission), and return the display to **IDLE**. Saved waypoints remain available. **Return home** plans a mission back to the configured Home, including its heading; cancel an active mission first.
5. Save the selected goal into slots **A**, **B**, or **C** using each row's save icon. **Use current robot pose** selects the live pose for saving. Slots can be overwritten or deleted; active mission goals are copied and do not change when a saved slot is edited.
6. Use **+** beside saved slots to build a sequence of up to 12 visits, including repeated slots. Click a sequence chip to remove it. Choose **Run waypoint sequence**, or use a row's play icon for a single waypoint. All legs must have valid paths before the mission starts.

Drag the map to pan, or select **Pan**. Use zoom and reset controls in the toolbar. The cyan square and wheels show the virtual AMR; its clearance ring covers the square chassis at every heading plus a 25 mm margin. Orange indicates the selected goal/heading, dashed blue is the planned route, and teal is the traveled trajectory. Selecting an occupied or insufficient-clearance destination reports an error and never starts motion.

The fixed warehouse is **8 × 6 m**, with **0.20 m cells**. Planning uses footprint-aware **4-connected A*** and a conservative circular envelope (about 0.202 m radius). The follower turns toward each path point, advances slowly, then aligns final yaw. Completion tolerances are **35 mm** and **0.035 rad** (about 2°). Poses use SI units, yaw radians, a `map` frame, and row-major occupancy metadata, leaving a clear boundary for a future OccupancyGrid/TF adapter. There is no ROS transform subscription.

The audited route is **A=(2,1,0), B=(2,2,0), C=(1,2,0), then Home=(1,1,0)**. Tests verify every visit and independent home-to-A/B/C round trips. A longer obstacle-detour example is (4.5,1,90°). Crossing the central wall requires a detour; the planner checks all segments against the inflated footprint. The educational follower can take a minute or more for longer missions at these wheel speeds.

## Phase 3: persistent Home and waypoints

On **Navigation**, choose a map destination and heading, then select **Set Selected as Home**. **Set Current Pose as Home** copies the authoritative current pose. **Reset Default Home** restores (1,1,0). Settings also offers current-pose and default-Home actions. The saved Home is displayed with coordinates and heading and uses a distinct gold diamond/H marker with a heading line.

Every Home update is checked against the map and the same footprint clearance as navigation. Home changes are rejected while a mission is **running or paused**, including through the API; rejection does not pause the mission or change its owner. A change never teleports or resets the current robot, encoders, wheels or trajectory. Return Home always plans to the currently saved Home. Only a **new backend session** initializes pose at saved Home, stationary with zero encoders.

The default configuration file is **`backend/data/robot-config.json`**, excluded from Git. It stores version 1, Home, and A/B/C waypoint poses/headings, not measured telemetry or active missions. Override its location using an absolute `ROBOT_CONFIG_PATH` when starting Uvicorn. `ROBOT_CONFIG_PATH=:memory:` explicitly disables persistence, primarily for isolated browser tests.

Saves write a temporary file in the same directory, flush/fsync it, then atomically replace the destination. In-memory configuration is updated only after successful replacement. Permission/disk failures report an error and leave the previous configuration in memory and on disk. Use a **single backend worker/process** per configuration file; cross-process editing is not supported. Local storage must be writable. No system installation is needed.

Startup validates Home and every waypoint against the active map. Invalid Home falls back to default Home; invalid waypoints are skipped individually. A corrupt/unsupported file falls back to defaults with visible warning events and is left untouched until an explicit successful save. If neither saved nor default Home has clearance, startup fails rather than creating an unsafe initial pose. Load warnings are cleared after a successful configuration save; historical warning events remain until evicted.

A/B/C save, overwrite and delete actions persist immediately. Existing mission goals are copied, so editing saved slots cannot alter an active sequence. Configurations are shared across tabs; draft goals and sequence edits remain local to the Navigation view.

Home commands work over the WebSocket or `POST /api/configuration`:

```json
{"type":"configuration","action":"set_home","goal":{"x":2,"y":2,"yaw":1.570796}}
{"type":"configuration","action":"current_home"}
{"type":"configuration","action":"reset_home"}
```

The POST API returns the updated configuration, **409** for Home changes during running/paused missions, **400** for clearance/storage failures, and **422** for invalid request fields. WebSocket business-rule failures return an error frame without altering motion ownership. Configuration files should be backed up separately if needed; no cloud storage is used.

## Phase 3: diagnostics and exports

- **Motors:** target/actual RPM, signed tracking error (`target − actual`), independent normalized/raw encoders, wheel velocity, estimated signed net wheel travel, requested/limited/measured body motion, saturation, watchdog state, STOP latch/reason and pose clearance. RPM saturation proportionally scales targets to ±40 RPM. Travel is derived from full-resolution normalized encoder integration, not rounded displayed counts.
- **Response history:** actual/target charts for both motors over up to 600 samples (approximately 60 seconds). Overview keeps its existing 15-second chart window.
- **Future PI telemetry:** per-motor `pi` fields (`kp`, `ki`, `pwm`, `control_error`, `integral_term`) are **null / Unavailable** with source `unavailable`. No PI gains, PWM or integrator values are invented; the plant is acceleration-limited, not the ESP32 firmware PI controller. The UI reads these fields from the telemetry contract for future explicitly sourced data.
- **System Health:** synthetic CPU, RAM, temperature and battery history. These are not Raspberry Pi or battery sensor readings. Some synthetic channels are intentionally constant.
- **Communication:** disabled ROS 2 Humble and UART contracts. Planned nodes/topics and 20/10/15 Hz rates are proposed design targets, not verified runtime frequencies. `/diagnostics` compatibility is planned as `diagnostic_msgs/DiagnosticArray`. ROS message timestamps/observed rates remain null. UART is planned for **57600 baud**, but heartbeat/watchdog, TX/RX, hardware command/fault counters and message timestamps remain null/unavailable. WebSocket service counters are shown separately and never represented as UART activity.
- **Events:** filter INFO/WARNING/ERROR, case-insensitive keyword search and export matching backend events as CSV. CSV quoting preserves commas/quotes; formula-like string cells are escaped. Export errors are visible.
- **Freshness:** connection state, physical sample age and last-update time are displayed. Live motor measurements disappear on disconnect; retained charts/events are historical. Reconnection hydrates backend history. A new `session_id` clears prior-session chart samples rather than mixing reset encoders and motion histories.

The backend retains **600 compact history samples** and **60 events** in bounded deques. The frontend also caps history at 600 and deduplicates physical sample timestamps. Only the compact measurements are buffered, not copies of full paths/trajectories. CSV telemetry exports include timestamp/session/source, pose, requested/measured body motion, both target/actual/error RPMs, encoders, wheel travel, saturation and system health. Exports use the backend's current retained buffer and reset after backend restart. There is no unlimited logging or historical database.

Browser integration tests use ports 15173/18000 and **memory-only configuration**, never the developer's saved Home/waypoints. Python API tests use isolated temporary configuration files; persistence tests explicitly reopen the store across simulator/lifespan restarts.

## Phase 4A: Sensor Center

Open **Sensors** for two panels: **2D LiDAR Visualization** and **Front Camera Monitor**. Every panel identifies its source, status, timestamp/frame ID, freshness or unavailability, and planned ROS interface. All current sources are **SIMULATED**, **PLACEHOLDER** or **DISABLED**. No physical sensor, camera device, ROS graph, UART or GPIO is opened.

### Deterministic virtual LiDAR

Defaults are **180° field of view**, **181 beams**, **5 m maximum range**, and **5 Hz target scan rate**. These are **simulation defaults, not specifications of your physical LiDAR**. Backend contracts use meters and radians; the UI converts headings/FOV to degrees for display.

Rays originate at the authoritative robot's center with zero virtual mount offset, using its current map pose and yaw. Exact grid-cell traversal (DDA) stops at the first occupied/unknown cell or map boundary. Corner ties check adjacent occupied cells. There is no random noise, physical device query, interpolated pose engine or independent robot simulator.

Each cached scan includes:

- `angle_min`, `angle_max`, `angle_increment`, `range_min=0`, `range_max`, `beam_count`, `scan_time=0.2`, `time_increment=0`, units and map frame metadata.
- Finite `payload.ranges` and parallel `payload.hits` arrays. **No return** is `range_max` with `hit=false`; a real virtual intersection exactly at maximum range has `hit=true`. No Infinity/NaN is transmitted.
- `payload.acquisition_pose` with the map-frame x/y/yaw captured for that scan; `timestamp`, `sequence`, source and freshness.
- Minimum detected obstacle distance over **hit rays only**, or null if nothing is detected. A ray starting inside an occupied cell or outside the map reports a zero-distance hit.

The polar view points forward upward; positive angles are to the robot's left (CCW). Only hits are plotted: maximum-range no-return values do not create fake obstacles. **Show simulated LiDAR** on Navigation overlays world points transformed with the **scan's acquisition pose**, not a newer displayed robot pose. The overlay is optional and defaults off. No camera/laser visualization is used by A*, the footprint model or collision protection.

### Camera placeholder and future contracts

The camera remains **NOT_CONNECTED / PLACEHOLDER**. The visible color-bar pattern is static UI artwork, explicitly labeled **NO CAMERA FRAMES**, not a synthetic live feed. Frame timestamp, resolution, encoding, FPS and backend `stream_url` are null; zero camera frames have been received. The preview's layout dimensions do not represent camera resolution. There are no person, marker or object detections.

Future adapters implement the common `SensorAdapter.snapshot()` envelope in `backend/app/sensors/contracts.py`:

| Field | Meaning |
| --- | --- |
| `sensor_type` | `lidar_2d` or `camera` |
| `source` | `SIMULATED`, `PLACEHOLDER` or `DISABLED` in Phase 4A |
| `status` | `INITIALIZING`, `READY`, `STALE`, `ERROR`, `NOT_CONNECTED` or `DISABLED` |
| `timestamp`, `frame_id`, `sequence` | Acquisition identity, not an invented camera timestamp |
| `freshness` | Monotonic age in ms, stale flag and 1000 ms timeout |
| `metadata` | Type-specific scan/image information |
| `interface` | Planned topics/types with hardware connection state `DISABLED` |
| `payload` | Latest finite virtual ranges/hits/pose, or null for the camera |

Planned ROS 2 mappings are `/scan` → **sensor_msgs/LaserScan**, `/camera/image_raw` → **sensor_msgs/Image**, and `/camera/image_raw/compressed` → **sensor_msgs/CompressedImage**. No ROS package is imported. A future LaserScan adapter must validate/normalize range values and provide the scan-to-map acquisition transform before overlaying points. A future backend camera adapter must supply genuinely sourced frames, acquisition timestamps, dimensions/encoding/FPS and a same-origin `/api/` streaming URL. `CameraMonitor` has a conditional stream preview path, but the current placeholder always has a null URL and never requests frames. Hardware enablement is outside Phase 4A.

### Rate limits, fault isolation and stale states

The existing physics loop steps one `SensorManager`, which retains **only the latest scan** and one camera metadata snapshot. Repeated HTTP requests or extra clients do not rerun raycasting. Scheduling advances from simulation dt, captures once when the 0.2 s interval is due, and skips catch-up bursts after delays. There is no sensor history queue, image buffer or point-cloud history. Default single-scan JSON is tested below **8 KiB**, and status summaries below **4 KiB**; actual Pi 4 CPU/network performance still needs measurement on your device.

`/ws/sensors` publishes cached bundles only when scan sequence/status changes, with a 0.2 s minimum publish interval. The frontend subscribes only while Sensors or Navigation is open; Diagnostics uses compact summaries from `/ws/telemetry`, so full beam arrays are not added to the 10 Hz robot stream. Only one latest bundle is retained in the browser.

The sensor WebSocket is **read-only**: incoming messages close it with code 1008. It never owns motion, renews a control lease, disconnects a controller or alters a mission. Sensor stream disconnects/reconnects are independent of the control stream. Sensor adapter exceptions become visible error metadata and one warning/error event per failure episode; the physics, STOP, mission state and grid collision checks continue independently.

A scan older than **1 second** is stale. The browser also checks acquisition timestamps against its clock, hiding laser points and minimum distance for stale/disconnected/error states. Camera fields remain unavailable rather than being marked fresh. Sensor transport failures reconnect every two seconds. Session IDs prevent overlaying a scan from another backend session. UI times continue to use UTC+07 and backend acquisition timestamps use UTC ISO 8601.

Phase 4A limits: idealized 2D binary occupancy intersections; no glass/material effects, noise, occlusion beyond grid cells, intensity values, rolling scan motion, real calibration, extrinsics/TF subscription, image capture or detections. All beams are instantaneous at one pose (`time_increment=0`). The sensor sees raw occupied cells while navigation uses an inflated footprint; it is a visualization, not a safety sensor or obstacle-avoidance replacement.

## Navigation command examples

Send these over the existing WebSocket, with `heartbeat` messages every 150 ms while owning an autonomous mission:

```json
{"type":"navigation","action":"start","goal":{"x":2,"y":1,"yaw":1.570796}}
{"type":"heartbeat"}
{"type":"navigation","action":"pause"}
{"type":"navigation","action":"resume"}
{"type":"navigation","action":"cancel"}
{"type":"navigation","action":"home"}
{"type":"waypoint","action":"save","name":"A","goal":{"x":2,"y":1,"yaw":0}}
{"type":"navigation","action":"sequence","waypoints":["A","B","A"]}
{"type":"waypoint","action":"delete","name":"A"}
{"type":"release"}
{"type":"stop"}
```

`plan` accepts the same goal as `start`. Live navigation statuses are `idle`, `ready`, `running`, `paused` and `blocked`. Successful completion returns to `idle`; completed/cancelled outcomes are retained in `navigation.last_result` and event logs instead of lingering as live mission states. An idle mission has no destination, path, current waypoint or progress. Starting manual control discards an unused preview or acknowledged failed mission, so manual motion never inherits an old navigation label. Operating mode is `STANDBY`, `MANUAL` or `AUTONOMOUS`; a paused mission still reserves autonomous mode until cancelled.

## Safety behavior

All motion command handling remains in memory; only Home and waypoint configuration is written to local storage. There are no motor, UART, GPIO or ROS dependencies.

- Frontend sends a control heartbeat every 150 ms only while a direction is held.
- Manual pointer release/cancel, lost pointer capture, keyboard release, focus loss, hidden tab, page change, slider change and control unmount send an owner-scoped `release`. This stops manual motion without cancelling an autonomous mission or another client’s command. Page exit/unmount closes the controller connection.
- Manual motion stops immediately on release, owning-controller disconnect, invalid input or the **600 ms** manual-command watchdog. Heartbeats alone cannot keep a released manual command alive. The outer simulation loop evaluates watchdogs approximately every 100 ms.
- Autonomous missions reserve motion against manual commands while **running or paused**. Pause stops simulated wheels immediately. Cancel/STOP cancel the mission and zero targets and actual RPM immediately; this intentional safety stop bypasses ordinary deceleration. Any connected client may issue STOP.
- Autonomous missions receive a **150 ms** controller heartbeat and pause after **1.5 s** without it, or when the owning WebSocket disconnects. Reconnecting does **not** resume navigation automatically. Resume explicitly replans remaining legs from the actual pose; a new client may resume after the prior owner disconnects. Background-tab timer throttling can also safely pause a mission.
- Collision checking covers manual and autonomous motion. Each physics substep uses a continuous swept-disk check against occupied/unknown cells and map boundaries; path planning uses the same check. This detects grazing corners between the old sample positions. The radius is derived from the **250 × 250 mm** chassis: `hypot(0.125, 0.125) + 0.025 = 0.201777 m`, covering every chassis heading with a 25 mm margin.
- **Manual collision:** stop wheels/targets immediately, keep mission **IDLE**, and emit a warning identifying pose, required clearance and recovery guidance. The colliding held command is inhibited until input release or a changed command, preventing repeated restarts against the obstacle.
- **Autonomous collision:** stop immediately and set mission **BLOCKED**, retaining the failed destination/path and a clear reason. A blocked mission does not resume automatically. STOP or explicit cancellation clears it to IDLE; a valid new plan replaces it. If the actual pose itself is obstructed, restoring map/pose clearance is necessary before any route can start; STOP never teleports the robot.
- One collision warning is logged per source/episode. Held retries and stationary ticks do not duplicate warnings. A new encounter may warn after the robot moves at least **0.10 m** from the warning pose (or changes between manual and autonomous collision sources).
- Home clearance is validated when creating the simulator. HTTP/WebSocket telemetry includes `clearance.pose_clear` and `clearance.radius`; **Diagnostics** shows current pose clearance. Error messages distinguish an obstructed robot pose from an invalid destination.
- A stale telemetry stream is closed after approximately two seconds; reconnection starts with no pending drive command.
- The input envelope accepts ±0.6 m/s and ±2.0 rad/s, then **proportionally scales both wheel targets** to enforce ±40 RPM even for combined linear/angular commands. This preserves commanded curvature. The maximum straight speed is about **0.1822 m/s**; UI sliders use 0.02–0.18 m/s and 0.2–1.2 rad/s. Non-finite values, unknown commands and extra fields are rejected.
- One WebSocket client can own motion at a time. Other clients can observe; any connected client may issue STOP. This is a local development simulator without authentication, not a hardware safety system.

## HTTP and WebSocket API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Service health, `simulation: true`, `hardware_enabled: false` |
| `GET /api/robot/status` | Current shared simulator snapshot |
| `GET /api/map` | Static row-major simulated occupancy grid with origin, resolution, frame and clearance radius |
| `GET /api/configuration` | Saved Home, A/B/C waypoints, storage mode and startup validation warnings |
| `POST /api/configuration` | Validated `set_home`, `current_home`, `reset_home` commands |
| `POST /api/waypoints` | Validated save/delete waypoint commands |
| `GET /api/events?level=warning&q=collision&format=csv` | Filtered bounded event export (`format=json` by default) |
| `GET /api/diagnostics/history?limit=600&format=csv` | Retained compact telemetry export (`format=json` by default) |
| `WS /ws/telemetry` | 10 Hz snapshots, compact sensor status summaries and simulated control input |
| `GET /api/sensors` | Latest sensor summaries and simulation session ID; no beam arrays |
| `GET /api/sensors/lidar` | Latest cached virtual scan, metadata, hit mask and acquisition pose |
| `GET /api/sensors/camera` | Disconnected camera placeholder metadata; no frames |
| `WS /ws/sensors` | Read-only cached sensor bundles, at most 5 Hz |

Control message (repeat while held):

```json
{"type":"control","linear":0.25,"angular":0.0}
```

Stop message:

```json
{"type":"stop"}
```

Telemetry contains `type`, `simulation`, UTC `timestamp`, `mode`, `uptime`, measured simulated `linear_velocity`/`angular_velocity`, `motors`, `health`, `events`, `pose`, `home`, `trajectory`, `drive`, `clearance`, `configuration`, `diagnostics`, `session_id`, `sensors` and `navigation`. Navigation includes status, progress, active destination, current waypoint/index, planned path and saved waypoints. Each motor provides `target_rpm`, `actual_rpm`, normalized signed `encoder_count` and `raw_encoder_count`. UI event/history timestamps consistently use **Asia/Ho_Chi_Minh (UTC+07)**; exports retain UTC ISO 8601 timestamps. Sample timestamps refer to the last physics update, not each HTTP/WebSocket read. Error frames use `{"type":"error","message":"..."}`. Successful one-shot commands receive `{"type":"ack"}`; telemetry remains the authoritative result.

Browser WebSocket origins are checked. Defaults allow localhost/127.0.0.1 on ports 5173 and 4173. For a different local origin, set a comma-separated `ALLOWED_ORIGINS` when starting the backend. No wildcard is used by default.

## Architecture and future ROS integration

```text
frontend/
  src/App.tsx                    Page composition and navigation
  src/components/ManualControl.tsx  Hold/release control interactions
  src/components/RpmChart.tsx     Shared Recharts chart (±40 RPM scale)
  src/components/NavigationPage.tsx  Goal, waypoint and mission UI
  src/components/NavigationMap.tsx   SVG map rendering and interactions
  src/components/MissionSummary.tsx  Shared pose/mode/progress readout
  src/components/SensorsPage.tsx    Sensor Center composition and status
  src/components/sensors/          Polar scan and camera placeholder components
  src/hooks/useSensors.ts          Independent read-only stream and freshness
  src/sensors.ts                   Sensor contracts, validation, map transforms
  src/components/HomeConfiguration.tsx  Saved Home actions
  src/components/DiagnosticsPage.tsx  Diagnostics tabs and freshness
  src/components/diagnostics/       Motors, health, communication and events
  src/utils/telemetry.ts            Consistent timestamps, history merge, CSV downloads
  src/hooks/useRobot.ts          WebSocket lifecycle, history, reconnect, heartbeat
  src/types.ts                   Telemetry/control types
  src/styles.css                 Tailwind import and responsive mission-control theme
  tests/dashboard.spec.ts        Browser integration checks
  vite.config.ts                API/WebSocket proxy
backend/
  app/main.py                   FastAPI routes, lifespan, streaming, ownership cleanup
  app/models.py                 Validated command contract
  app/simulator.py              Single simulation coordinator and arbitration
  app/state.py                  Authoritative pose, wheels, encoders and trail
  app/drive.py                  Saturated kinematics, acceleration and pose math
  app/navigation.py             Occupancy grid, footprint collision checks, A*
  app/mission.py                Waypoints, mission lifecycle and path follower
  app/telemetry.py               Shared HTTP/WebSocket state serialization
  app/configuration.py           Validated Home/waypoints and atomic persistence
  app/diagnostics.py             Simulated measurements and future interface contracts
  app/exports.py                 Event filtering and CSV formatting
  app/sensors/contracts.py       Transport-neutral sensor envelope / adapter protocol
  app/sensors/lidar.py           Deterministic finite grid rays and virtual scans
  app/sensors/camera.py          Metadata-only disconnected camera placeholder
  app/sensors/manager.py         Single bounded cache and 5 Hz scheduling
  data/robot-config.json         Runtime configuration (ignored by Git)
  tests/                        API and simulator safety tests
  requirements.txt              Direct dependencies
  requirements.lock.txt         Tested dependency versions
```

Geometry: wheel radius **0.0435 m**, separation **0.300 m**, encoder resolution **approximately 3960 counts/revolution**. Targets use `left = (v − ω × separation / 2) × 60 / (2π × radius)` and the corresponding plus sign for the right wheel. Encoders integrate signed wheel revolutions. Planned UART baud is displayed as **57600, disabled**.

The frontend never integrates robot pose or creates a second simulation. HTTP and WebSocket serialize the same backend state. The API and UI are independent of the plant implementation. A later phase can introduce an explicit robot adapter implementing the simulator's command, stop, disconnect, tick and snapshot contract, with an rclpy bridge behind it. That future phase must define its hardware command ownership, watchdog and authentication separately. No hardware integration is included here.

## Phase 4A verification and limits

Verified: **109 backend tests**, **13 browser integration tests**, and the frontend production build pass. The build reports a non-blocking large-chunk warning; the backend test dependency reports an AnyIO deprecation warning.

Audit regressions cover manual versus autonomous collisions, warning deduplication, held-input inhibition, STOP/cancel after blocking, idle state cleanup, footprint boundary/corner clearance, continuous grazing-corner collision detection, the observed dashboard pose clearance, exact A/B/C sequence visits and return home, independent wheel encoder integration, and odometry invariance under raw encoder polarity changes. Phase 3 adds Home/current-pose/reset validation and persistence, no-teleport checks, configured Return Home, waypoint heading restore/overwrite/delete/sequence, corrupt-file fallback, failed-write rollback, diagnostics calculations, unavailable PI/UART data, bounded history, filtering/CSV escaping, STOP/disconnect status and stable session/sample timestamps. Automated backend tests also cover forward/inverse kinematics, combined-command RPM saturation, smooth wheel ramps, forward/reverse/arc/spin integration, encoder polarity, waypoint management, full sequence execution, obstacle detours, unreachable destinations, final yaw, return home, mission progress, command arbitration, pause/resume, STOP, collision guarding, disconnect and lease expiry. Phase 4A adds deterministic ray distances, translation/rotation, boundary/unknown/corner/max-range behavior, no-return classification, sensor scheduling/payload budgets, pose immutability, disconnected camera, read-only sensor transport and fault isolation. Browser tests exercise real UI/WebSocket integration, polar/overlay rendering, stale/disconnected/invalid sensor states, mission continuity during sensor outages and responsive layouts.

This is an **educational navigation simulation, not production-grade Nav2**. The map is static; there are no dynamic obstacles, SLAM, localization uncertainty, wheel slip, torque, battery physics or live sensors. The conservative circular footprint can reject passages that a precisely oriented square could fit. A collision guard stops rather than replanning automatically. Test-only obstacle injection exercises runtime blocking; there is no dynamic-map editing UI. Each short curved integration step is guarded using its endpoint chord and a conservative footprint margin; this is not a continuous curved-body physics engine. Mission progress reflects consumed path points, rather than a time or distance estimate. Home and valid waypoints persist; live missions, encoders, diagnostics counters, histories and event logs reset with the backend. New sessions initialize pose at saved Home; the trail retains 1200 points. Use one worker. Telemetry currently includes the bounded path and trail at 10 Hz; larger maps would need separate map/path transport. Saved waypoint slots are shared across browser clients; selected draft goals and sequence edits are local to the Navigation view.

Raw encoder polarity defaults to **left +1, right −1**, and remains configurable using `DriveConfig(encoder_polarity=(1, -1))` when constructing a simulator. Each wheel independently integrates its own average RPM over each physics substep. Normalized counts use positive-forward wheel motion on both sides, and differential-drive pose integration always uses normalized wheel RPM, so raw polarity cannot reverse odometry; `raw_encoder_count` applies the configured sign. This is configuration for later adapters, not a hardware connection. No dependencies, ROS repositories or ESP32 repositories were changed for Phase 4A.

For alternate local API ports, set `VITE_PROXY_TARGET=http://127.0.0.1:<port>` when launching Vite, and include the UI origin in backend `ALLOWED_ORIGINS`. The defaults and normal run commands above are unchanged.

Implementation references: [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/) and [Tailwind's Vite integration](https://tailwindcss.com/docs/installation/using-vite).
# RobotAMR_WebDashboard
