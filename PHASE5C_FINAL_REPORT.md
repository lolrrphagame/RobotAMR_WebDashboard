# Phase 5C — final simulation acceptance report

Date: 2026-11-22 (Asia/Ho_Chi_Minh). **Automated simulation acceptance passed. A reviewed simulation baseline can be frozen with explicit manual acceptance exceptions. Mobile HTTPS trust, native Windows/Android acceptance and Raspberry Pi qualification remain pending. Hardware integration is not enabled.**

## Scope and preserved boundaries

The existing dark navy/cyan application was retained. One `RobotSimulator` supplies pose, differential-drive telemetry, Navigation and Mission Operations. API and socket consumers read that same state. Both production launchers keep a single Uvicorn worker. Local mode remains loopback-only; LAN mode requires authenticated Operator/Observer sessions behind Caddy HTTPS/WSS with the backend on 127.0.0.1.

No ROS/ESP32/UART/GPIO/motor/LiDAR/camera access, Pi deployment, sudo/system installation, firewall change or GitHub push occurred. The pre-existing user LAN service was left running and was not restarted; backend activation requires a coordinated graceful restart. Previous public hashed frontend assets were retained for already-open tabs without replacing the new build entrypoint. See acceptance/phase5c/retained-assets.json. Active-build size measurements exclude those compatibility files. Existing source-control changes to README, deployment documentation and the env example were preserved. Existing user databases, account files, private config and certificate/CA stores were not used for tests or restored over.

## Confirmed defects and measured optimizations

1. **Mission request overlap:** a one-second polling interval could start another pair of requests while the previous requests were still pending; leaving the page only ignored results. Polling now allows one in-flight pair and aborts it on exit. Delayed-response and failed-sibling browser regressions confirm one poll while blocked, abort of a failed pair, and successful retry.
2. **Repeated wire encoding:** the cached authoritative frame was still encoded separately for each telemetry socket. One encoded JSON string is now shared per frame/transition. Tick/STOP invalidation tests ensure this does not delay safety state.
3. **Archive reads:** summary/history APIs decoded the whole mission archive into Python before slicing. JSON reads now apply SQL limits (200 summary / 1000 history), calculate the full filtered count separately, and aggregate analytics in SQLite. Unicode casefold and literal search behavior are preserved. No schema/data migration was added. SQLite JSON support is checked before initialization writes.
4. **Backup resource/privacy handling:** backup relied on connection finalization rather than explicit close and inherited default directory/file permissions. It now closes both SQLite connections and creates a private 700 directory / 600 files. Existing destinations are still refused. Tests restore only into temporary paths.
5. **Cold login payload:** shared React dependencies previously pulled the chart bundle into initial login. Explicit React/vendor separation and a lazy RPM component defer charts until needed. The LAN browser test verifies no chart requests before login. The empty React-chunk build notice is eliminated.

No kinematics, collision, motion ownership, STOP inhibition, watchdog, mission execution or hardware-mode logic was changed. An early soak-tool run omitted the deliberate release required after STOP; the harness was corrected instead of weakening the latch. Test seeding was also moved to the ASGI event-loop thread rather than disabling SQLite's thread check.

## Final automated results

| Executed check | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| Backend pytest, including opt-in laptop private-interface HTTPS/WSS | 245 | 0 | 0 |
| Development Playwright | 16 | 0 | 0 |
| Local-production Playwright | 6 | 0 | 0 |
| Trusted-HTTPS LAN Playwright | 4 | 0 | 0 |
| Frontend production build | Yes | 0 | 0 |

Baseline before Phase 5C: 235 backend tests passed, one private-interface test skipped. Normal final pytest without `PBL4_LAN_TEST_IP` reports **244 passed / one explicit skip**. The final run supplied the laptop's current private interface explicitly and passed all 245. The new backend acceptance file contributes nine cases. The existing upstream Starlette/AnyIO deprecation notice remains; it is not a failed test.

Backend coverage includes authenticated roles, anonymous denial across private HTTP/socket endpoints, secure cookies, CSRF, Host/Origin/TLS validation, expiration/revocation of both streams, independent-Operator STOP, lease/watchdog/reconnect, navigation/collision/encoder/RPM regressions, deterministic sensors, Home/waypoint/mission persistence, backup and restart. No sensitive state streams before authentication.

Browser coverage includes all seven pages, responsive login and desktop/mobile viewports, same-origin WSS telemetry/sensors, Observer restrictions, Operator controls, page refresh, logout/revocation clearing private views, slow-poll cleanup, stale/disconnected/error states, and stable live socket counts across repeated navigation. Linux headless Chromium 159.0.8154.6 was available. This is not Windows, Android or native Brave execution.

## Measured performance

Host: Ubuntu 22.04.5 LTS, AMD Ryzen 9 8945HX, 32 logical CPUs, approximately 31.1 GiB RAM, Python 3.10.12, SQLite 3.37.2. Caddy uses the existing approved project-local binary. These are **laptop measurements**, not Pi estimates. Baseline application code was exported from local Git revision `967e024` into an isolated temporary directory; it was not checked out over the user's workspace. Baseline and final native runs use temporary accounts, CA, database and JSON configuration.

### Bounded component benchmarks

Mean wall times from [before](acceptance/phase5c/micro-before.json) and [after](acceptance/phase5c/micro-after.json), with p95 values retained in those artifacts:

| Operation | Before | After |
| --- | ---: | ---: |
| Physics tick (200 samples) | 0.8690 ms | 0.9819 ms |
| 181-beam LiDAR scan (200) | 1.2145 ms | 1.2182 ms |
| Snapshot + JSON encoding (200) | 0.0635 ms | 0.0629 ms |
| Four consumers / authoritative frame (200) | 0.1690 ms | 0.0727 ms |
| 1000-run archive: 200 history rows + analytics (30) | 11.8930 ms | 3.4137 ms |

The targeted shared-encoding and archive-query costs decreased. Physics/raycast algorithms were not optimized or changed; their small timing variation is not evidence of improvement/regression. The archive fixture has 1000 synthetic terminal runs, not copied user data. CSV still intentionally exports the full matching archive; large-export memory and archive retention remain limitations.

### Authenticated HTTPS workload and soak

One Operator and three read-only Observer clients each receive telemetry and sensor streams (eight live sockets). Observer clients reuse one isolated Observer account/session; role semantics are also tested separately with distinct users. The Operator issues explicit WAIT → nearby pose → Home missions. Observer sockets reconnect periodically. HTTP measurements are a **sequential pair** of GET diagnostics/history and GET missions, not a single-request or STOP latency SLA.

| Run | Backend CPU, one core | Backend RSS | Caddy CPU, one core | HTTP pair p95 |
| --- | ---: | --- | ---: | ---: |
| Baseline 30 s | 4.83% | 50.51 → 55.01 MiB | 0.80% | 22.38 ms |
| Final 30 s | 4.26% | 50.40 → 54.40 MiB | 0.77% | 20.28 ms |
| Extended 120 s | 6.40% | 50.39 → 57.84 MiB | 0.86% | 41.92 ms |

The 30-second samples show a modest end-to-end difference, but are not repeated statistical trials. The longer sample has more history, events and trajectory data; do not compare its CPU/latency as an equal-size workload or claim a general throughput speedup. CPU is `/proc` process CPU time divided by elapsed wall time, normalized to one core, not percent of all 32 host CPUs and not the Dashboard's simulated health value.

The final 30-second workflow passed **18 checks**, including anonymous/Observer denial, real mission execution, STOP/cancel, logout during motion, socket cleanup, camera placeholder, online WAL backup, isolated integrity/JSON restore, restart session revocation, stopped recovery, retained Home/waypoints/history, unchanged CA and bounded buffers. Five Observer reconnects occurred; no stream errors were recorded. Backend FDs remained 25 during load and dropped to 17 after stream cleanup; Caddy FDs remained 23 and dropped to 7.

The 60-second run passed its 15 checks with no errors. The 120-second run completed five missions and started six before the final safety scenarios. Backend RSS rose 50.39 → 57.84 MiB (+7.45 MiB), then was nearly flat around 57.7–57.8 MiB during approximately seconds 63–120. FDs remained 25 (backend) / 23 (Caddy). The history/event buffers reached their limits (600/60); trajectory retained 143 of its 1200 capacity. Warming buffers/allocators explain part of initial growth, but **two minutes cannot prove absence of long-run leaks**.

Raw stream payload totals (UTF-8 JSON application bytes; exclude transport framing, compression, TLS/TCP/IP overhead):

- Final 30 s: 9,543,980 telemetry bytes, 2,240,705 sensors bytes.
- Extended 120 s: 61,172,055 telemetry bytes and 8,891,723 sensor bytes across all clients.
- Observed aggregate rates are approximately 9.8 telemetry and 4.9 sensor messages/second per client, near the 10/5 Hz targets; reconnect gaps and scheduling affect counts. The simulator retains one current scan, not an unbounded sensor archive.

### Frontend and browser resources

Initial login JavaScript decreased from **714,246 bytes to 260,569 bytes (63.5% raw reduction)**. Total application code remains available lazily; this is not removal of features. [Current sizes](acceptance/phase5c/bundle-final.json) include per-file raw bytes and gzip estimates. The deployment was not changed to add HTTP compression; gzip estimates are not claimed as actual transferred bytes. The chart dependency chunk is now loaded only when used, verified in the HTTPS login test.

A warmed headless Chromium profile compared the same live Overview view before/after 21 page transitions and a three-second active-chart window. Live sockets stayed at one telemetry stream, plus one sensor stream only on Navigation/Sensors. Collected JS heap was 6.34 → 9.25 MiB (delta 2.91 MiB); renderer task CPU was 0.72 seconds, and requestAnimationFrame cadence was about 60.1 Hz. This is rAF cadence, not chart data frequency or a physical mobile frame-rate guarantee. GC was explicitly collected before heap samples, history continued filling, and these short observations are not a long-run leak proof. Raw browser results: [browser.json](acceptance/phase5c/browser.json).

An additional bounded 12-cycle run covered **84 page transitions** with the same socket-count limits. Collected heap was **6.51 → 9.92 MiB (+3.41 MiB)**; renderer task CPU was 1.77 seconds and rAF cadence about 60.1 Hz. The greater transition count did not produce proportional socket/heap growth, but this is still a short observation, not a leak-free certification. See [browser-extended.json](acceptance/phase5c/browser-extended.json). Both before/after samples use the same live Overview view.

## Repeatable verification

From the repository with the existing project-local dependencies:

```bash
env -u PYTHONPATH backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run build
npm --prefix frontend run test:e2e
npm --prefix frontend run test:production
npm --prefix frontend run test:lan
```

To include the optional private-interface test, first inspect `ip -brief -4 address` and set `PBL4_LAN_TEST_IP` to the current owned RFC1918 laptop interface for pytest. No address is hardcoded into production configuration. The ordinary command above deliberately skips that network listener test.

Run the bounded native workflow against an isolated **loopback HTTPS LAN-mode** instance, never your real production URL/data:

```bash
env -u PYTHONPATH backend/.venv/bin/python backend/tools/phase5c.py   --seconds 30 --observers 3 --output "/tmp/pbl4-soak-$(date +%s).json"

env -u PYTHONPATH backend/.venv/bin/python backend/tools/phase5c.py   --micro --output "/tmp/pbl4-micro-$(date +%s).json"
```

Optional supervised longer test, **not executed for 1800 seconds in this phase**:

```bash
env -u PYTHONPATH backend/.venv/bin/python backend/tools/phase5c.py   --seconds 1800 --observers 3 --output "/tmp/pbl4-long-soak-$(date +%s).json"
```

The tool bounds duration to 15–3600 seconds and Observer clients to 0–6, refuses an existing report path, uses bounded queues/history/error samples, and signals its own temporary service for shutdown. Keep the laptop attended; Ctrl+C runs cleanup. It requires existing `.tools/caddy`, built frontend assets and project-local Python packages; it installs nothing. Short 30/60/120-second runs were executed. Longer runs and realistic archive-size/browser combinations remain manual.

Optional bounded browser navigation profiling (1–12 cycles; three by default):

```bash
PBL4_BROWSER_CYCLES=12 npm --prefix frontend run test:production -- --grep 'all pages remain'
```

Playwright stores its browser JSON profile as a test attachment/output. The native tool does not run an actual browser; refresh/render measurements come from Playwright separately.

## Startup, accounts, backups and troubleshooting

- Local production: `./start-dashboard.sh` or `./start-dashboard.sh --no-build` after building; URL `http://127.0.0.1:8000`. Never proxy local developer mode onto LAN.
- HTTPS LAN: `./start-dashboard-lan.sh --check`, then `./start-dashboard-lan.sh`; URL `https://<configured-host>:8443`. Keep exact private DNS, Host/Origin, Caddy bind and existing CA/state. Auto IPv4 selects only a supported private physical interface; it does not update DNS or live-rebind.
- Accounts: use the existing private `app.accounts` CLI to create Operator/Observer users, list, disable, reset passwords, set roles or revoke sessions. Passwords are interactive; there is no signup/admin HTTP endpoint. Preserve legacy credentials using explicit migration, never reset them for acceptance.
- Shutdown: Ctrl+C or SIGTERM to the printed supervisor, wait for application shutdown before restart. SQLite closes, motion stops, unfinished work becomes interrupted and no queued work auto-starts.
- Mission/config backup: `python -m app.backup NEW_PRIVATE_DESTINATION` under the backend venv. Accounts/private env and complete CA/fingerprint require separate protected backup. Restore into fresh isolated paths first, verify integrity and saved headings/history, and never copy only a running SQLite main file while ignoring WAL.
- See [deployment details](PHASE5B2_DEPLOYMENT.md), [recovery and ARM64 plan](RASPBERRY_PI_READINESS.md) and [manual checklist](FINAL_ACCEPTANCE_CHECKLIST.md) for exact procedures.

If SQLite JSON is unavailable, startup now explains the required feature; verify the Python SQLite build rather than modifying data. A failed soak writes a failure report; inspect its checks/errors. DNS mismatch, ambiguous routes or certificate warnings require fixing private DNS/network/identity/trust, not relaxing allowlists/TLS. Missing Caddy/assets/dependencies require the existing local installation/build steps, never automatic system installation. For large archives, budget CSV and analytics costs and use verified backups; no retention deletion is performed automatically.

## Manual acceptance and freeze decision

**Ubuntu Brave CA import is user-reported and preserved.** Native Brave was not available in the automation environment, so a complete Brave workflow is not newly verified. **Mobile HTTPS trust is pending and is not accepted as verified.** Windows Chrome/Edge and actual Android execution are also unverified. Mobile viewport tests do not substitute for real device trust, touch/background behavior or network tests. Never bypass certificate warnings.

Other pending items: cross-device private DNS and backend-port refusal, actual Wi-Fi/DHCP handover, router/firewall exposure review, a supervised longer soak and larger archive/export test, protected account/CA recovery drill, actual ARM64 dependency installation/runtime, Pi thermal/storage/CPU/RAM measurements, and an approved permanent-service/log-retention policy.

**Recommendation:** freeze the reviewed simulation code/protocol baseline with the explicit checklist exceptions; do not claim complete mobile/LAN field acceptance or Pi/hardware qualification. Keep hardware adapters disabled. Future ROS/ESP32 work needs its own versioned adapter/command-gateway safety plan, real diagnostics provenance, independent watchdogs and supervised hardware validation. The planned boundary is documented in RASPBERRY_PI_READINESS.md; no driver or hardware command path was implemented here.

## Changed files and evidence

Runtime changes: `backend/app/simulator.py`, `main.py`, `operations.py`, `backup.py`; frontend `src/App.tsx`, `src/components/MissionsPage.tsx`, `vite.config.ts`. Acceptance tools/tests: `backend/tools/phase5c.py`, `backend/tests/test_phase5c.py`, `frontend/production-tests/acceptance.spec.ts`, and the cold-login assertion in `frontend/lan-tests/dashboard.spec.ts`. Documentation: this report, Raspberry Pi readiness, final checklist and README. Existing network-portability edits to deployment docs/example were retained.

Sanitized measured evidence is in [acceptance/phase5c](acceptance/phase5c): baseline/final component measurements, native workload/soak resources, browser profile, final bundle sizes, dependency metadata and a result manifest. No credentials, session cookies, private keys or production records are included. The micro-after artifact's bundle list predates the final chart split; use bundle-final.json for current frontend sizes.
