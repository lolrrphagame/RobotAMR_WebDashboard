# PBL4 AMR Mission Control — Phase 1

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

Open **http://127.0.0.1:5173**. API documentation is at **http://127.0.0.1:8000/docs**. Stop each server with `Ctrl+C`. Use one backend worker: simulated state lives in memory and resets on restart.

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

Stop the normal dev servers first: these tests start their own frontend/backend on ports 5173 and 8000. Tests cover live telemetry, pointer release, keyboard controls, focus loss, mobile overflow, disconnect/reconnect and disabled controls. If Chromium reports missing OS libraries, have your administrator supply them; do not use `install --with-deps` without approval.

## Dashboard

- **Overview:** connection, operating mode, linear/angular velocity, both wheel RPMs, two target/actual RPM charts, encoder counts, system health and event stream.
- **Manual Control:** the same telemetry and hold-to-drive controls. Hold a directional button using mouse/touch or focus it and hold Enter/Space. Releasing stops the simulated robot. Use STOP at any time. Space outside buttons and input controls also stops.
- **Navigation:** clearly labeled future-phase placeholder. LiDAR, camera, maps and goal planning are not implemented in Phase 1.
- **Diagnostics:** simulated CPU, memory, temperature, battery, encoders, interface state and logs.
- **Settings:** read-only robot geometry and simulation configuration.

Charts retain the most recent 150 samples (approximately 15 seconds at 10 Hz). The virtual robot starts stationary; hold a direction to see target and actual RPM responses. Wheel response uses a simple first-order lag, not an actual PI controller or a measured hardware model. Health values are synthetic. Event history is bounded to 60 entries and is not persisted.

## Safety behavior

All command handling is in memory. There are no motor, UART, GPIO or ROS dependencies.

- Frontend sends a control heartbeat every 150 ms only while a direction is held.
- Pointer release/cancel, lost pointer capture, keyboard release, focus loss, hidden tab, page exit, page change, slider change and unmount clear the command.
- Backend clears commands and simulated wheel speed when the owning controller disconnects, sends STOP, sends an invalid command, or misses the **600 ms** watchdog deadline. The simulation loop evaluates the watchdog approximately every 100 ms.
- A stale telemetry stream is closed after approximately two seconds; reconnection starts with no pending drive command.
- Linear velocity is limited to ±0.6 m/s and angular velocity to ±2.0 rad/s. Non-finite values, unknown commands and extra fields are rejected.
- One WebSocket client can own motion at a time. Other clients can observe; any connected client may issue STOP. This is a local development simulator without authentication, not a hardware safety system.

## HTTP and WebSocket API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Service health, `simulation: true`, `hardware_enabled: false` |
| `GET /api/robot/status` | Current shared simulator snapshot |
| `WS /ws/telemetry` | 10 Hz snapshots and simulated control input |

Control message (repeat while held):

```json
{"type":"control","linear":0.25,"angular":0.0}
```

Stop message:

```json
{"type":"stop"}
```

Telemetry contains `type`, `simulation`, UTC `timestamp`, `mode`, `uptime`, measured simulated `linear_velocity`/`angular_velocity`, `motors`, `health`, and `events`. Each motor provides `target_rpm`, `actual_rpm` and signed `encoder_count`. UI timestamps are displayed in the browser's local timezone. Error frames use `{"type":"error","message":"..."}`.

Browser WebSocket origins are checked. Defaults allow localhost/127.0.0.1 on ports 5173 and 4173. For a different local origin, set a comma-separated `ALLOWED_ORIGINS` when starting the backend. No wildcard is used by default.

## Architecture and future ROS integration

```text
frontend/
  src/App.tsx                    Page composition and navigation
  src/components/ManualControl.tsx  Hold/release control interactions
  src/components/RpmChart.tsx     Shared Recharts chart
  src/hooks/useRobot.ts          WebSocket lifecycle, history, reconnect, heartbeat
  src/types.ts                   Telemetry/control types
  src/styles.css                 Tailwind import and responsive mission-control theme
  tests/dashboard.spec.ts        Browser integration checks
  vite.config.ts                API/WebSocket proxy
backend/
  app/main.py                   FastAPI routes, lifespan, streaming, ownership cleanup
  app/models.py                 Validated command contract
  app/simulator.py              Pure simulation and differential-drive math
  tests/                        API and simulator safety tests
  requirements.txt              Direct dependencies
  requirements.lock.txt         Tested dependency versions
```

Geometry: wheel radius **0.0435 m**, separation **0.300 m**, encoder resolution **approximately 3960 counts/revolution**. Targets use `left = (v − ω × separation / 2) × 60 / (2π × radius)` and the corresponding plus sign for the right wheel. Encoders integrate signed wheel revolutions. Planned UART baud is displayed as **57600, disabled**.

The API and UI are independent of the plant implementation. A later phase can introduce an explicit robot adapter implementing the simulator's command, stop, disconnect, tick and snapshot contract, with an rclpy bridge behind it. That future phase must define its hardware command ownership, watchdog and authentication separately. No hardware integration is included here.

Implementation references: [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/) and [Tailwind's Vite integration](https://tailwindcss.com/docs/installation/using-vite).
# RobotAMR_WebDashboard
