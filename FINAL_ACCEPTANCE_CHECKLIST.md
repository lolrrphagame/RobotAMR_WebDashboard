# Final acceptance checklist — Phase 5C

Date: 2026-11-22. Status: **automated simulation acceptance passed; cross-device and Pi acceptance pending**. Results and measurements: [final report](PHASE5C_FINAL_REPORT.md). This checklist does not certify hardware safety.

## Executed automated acceptance

- [x] Backend regression suite: all current navigation, collision, footprint, encoder, RPM, STOP, watchdog, command-arbitration and mission tests executed.
- [x] Overview, Manual Control, Navigation, Missions, Sensors, Diagnostics and Settings render in headless Linux Chromium.
- [x] All seven pages fit desktop and 390×844 mobile viewport without horizontal overflow; login is responsive.
- [x] Repeated page transitions retain one telemetry socket and one additional sensor socket only on Navigation/Sensors; no growing live socket count was observed.
- [x] Existing loading, disconnected, stale/invalid sensor and error UI tests pass.
- [x] Slow Missions polls are single-flight and aborted on exit; delayed-response regression passes.
- [x] Anonymous LAN visitors see only login/public assets/minimal health/session; private APIs and socket handshakes are rejected.
- [x] Authenticated Observer monitoring works; controls, STOP, mission/configuration mutations and account administration remain unavailable.
- [x] Operator login, commands, independent-Operator STOP, CSRF, secure cookies, Host/Origin rules, logout and role/session revocation pass backend/LAN tests.
- [x] Expiration/revocation closes both sensitive streams and stops/pauses ownership; logout clears private browser views.
- [x] HTTPS/WSS tests verify certificates using an isolated CA; no ignore-certificate or TLS-bypass flags are used.
- [x] Cold anonymous login does not request chart chunks; no server account/env markers or known test passwords were found in built JavaScript/HTML.
- [x] Local mode remains loopback-only; LAN keeps authentication, a loopback-only backend and strict proxy boundaries.
- [x] Native 30/60/120-second workloads exercise one Operator, three Observer clients, sensor streams, navigation/operations, reconnects, cancellation, STOP and logout during motion.
- [x] Live SQLite/WAL backup, isolated restore, Home/waypoint/history preservation and restart with stopped motion were checked.
- [x] New backup directories/files are private, both connections close explicitly, and existing destinations are refused.
- [x] All acceptance data/accounts/certificates were temporary; no production restore, credential reset, CA regeneration or hardware access occurred.
- [x] Actual CPU/RSS/payload/query/bundle/browser measurements are recorded; Dashboard health values are not used as real host metrics.

## User-reported evidence

- [x] **Ubuntu Brave private Caddy CA imported — user-reported.** The user's existing trust/profile was preserved. This is not a newly executed Brave end-to-end test.

## Pending manual acceptance — do not mark complete from Chromium emulation

- [ ] **Mobile HTTPS certificate trust: NOT VERIFIED / NOT ACCEPTED.** Verify the public root fingerprint through a trusted channel, install trust using the device's approved process and open the exact HTTPS hostname without a certificate warning. Never bypass warnings.
- [ ] Ubuntu Brave: actual-hostname Operator/Observer login, all pages, STOP, logout, reconnect and valid session refresh using the already imported CA. Native Brave was not available to the automation environment.
- [ ] Windows Chrome and Edge: verified CA trust/private DNS, both roles, WSS telemetry/sensors, no unauthorized controls, refresh, independent-Operator STOP and logout/revocation.
- [ ] Android browser/device: actual touch controls and release/cancel, readable charts/map, mobile navigation, both roles, TLS/WSS, background/screen-lock disconnect behavior, and logout. Viewport emulation is not Android execution.
- [ ] Cross-device backend-port refusal and no public/IPv6/tunnel/router port-forward exposure; inspect the existing firewall/router policy without weakening it.
- [ ] Actual Wi-Fi/DHCP change: graceful stop, private DNS update, startup `--check`, restart with the same hostname/CA, fresh login and no automatic motion resume.
- [ ] Administrator restore drill for the real protected backup set, including accounts/env/CA; restore to isolated paths first. Do not overwrite production data for acceptance.
- [ ] A supervised longer soak (e.g. 1800 seconds) with realistic archive size and users. Review memory trend, resource cleanup, query/CSV behavior, log growth and free disk space. Two minutes does not prove absence of long-run leaks.
- [ ] Approved Raspberry Pi ARM64 setup/install/runtime tests, resource/thermal/storage measurements, service/log retention, backups and graceful power-loss/recovery assessment. No Pi was accessed.

## Manual test sequence

1. Confirm correct server hostname/private DNS and verified certificate trust. A warning stops acceptance until trust/name/clock/chain is corrected.
2. Anonymous: direct visits to Navigation/Sensors/Missions must show login; `/api/map` and private APIs must return 401; private sockets must not stream.
3. Observer: sign in, inspect all read-only pages and history. Confirm movement, STOP, Home/waypoint/settings and mission edits/execution remain disabled and backend mutations return 403.
4. Operator: run a short simulated mission, refresh and verify pause; explicitly resume/cancel. Hold a manual direction and release; verify stop. Have another independently signed-in Operator issue STOP.
5. Logout or revoke an owner during motion: views clear, sockets close and simulated motion stops/pauses. Refresh and restart must never resume motion automatically.
6. Navigate repeatedly, check for console errors/overflow, then disconnect Wi-Fi/background the browser. Reconnect safely without replaying held input.
7. Record browser/OS/device/date, CA fingerprint verification, exact hostname and observations. Never record passwords, hashes, session cookies or private keys in this checklist.

## Freeze decision

A reviewed **simulation baseline may be frozen with these explicit exceptions**. Do not label mobile/LAN field acceptance complete, Pi deployment qualified, or hardware integration ready. Complete mandatory manual checks and approve a separate hardware integration plan before changing any source/mode safeguards.
