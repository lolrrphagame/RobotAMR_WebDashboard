# Phase 5A audit

Scope: local frontend/backend, persistence, configuration, tests and docs. Simulation only. No production data reset, hardware access, system installation or push.

| Severity | Finding | Resolution / evidence |
| --- | --- | --- |
| Critical | HTTP mutations and control WebSockets were unauthenticated | Explicit LAN configuration, HTTPS-only sessions, operator/observer authorization, CSRF, host/origin validation. `test_security.py` exercises denial and operator access. |
| High | Another client's STOP could be undone by held manual heartbeat replay | Previous controller inhibited until release/disconnect; browser stop-generation handling. Regression covers authenticated second-socket STOP and replay. |
| High | Invalid/business commands disconnected the owner and paused valid missions | Rejections no longer mutate robot state. Existing invalid-input regression updated to assert preserved ownership. |
| High | SQLite save failures could bypass later STOP cleanup or end the physics task | Halt before persistence, terminal save-failure handling, storage-fault pause and restart requirement. Injected SQLite failure test verifies zero targets/actual RPM. |
| Medium | Shutdown cleanup could be skipped by exceptions | Finally-based halt/task join/SQLite close; unfinished runs remain interrupted. Recovery suite preserved. |
| Medium | No schema marker / lock timeout / WAL backup procedure | Compatible version-0 adoption to version 1; status index, busy timeout, passive close checkpoint, read-only online backup utility and preservation tests. |
| Medium | React socket callbacks could update after disposal | Disposed/current-socket guard; auth refresh before reconnect; no pending motion restored. |
| Medium | Heavy initial bundle and duplicate per-observer telemetry preparation | Lazy page imports, chart/vendor chunks, one cached prepared frame per physics update/transition. Build executed; no invented Pi benchmark. |
| Medium | Inputs, sessions and connections had insufficient limits | Bounded HTTP body, login/mutation/control rates, session/rate tables and WebSocket count. Observer command attempts close the connection. |

Security model: local mode trusts loopback programs only. LAN explicitly permits anonymous read-only monitoring; mutations/control need one shared operator credential. HTTP-only LAN is rejected. In-memory eight-hour sessions are revoked on logout/restart; HTTPS Secure/HttpOnly/Strict cookies and in-memory CSRF token. TLS proxy and credential provisioning are deployment prerequisites, not installed here.

Data: no table rewrite, history deletion or JSON reset. Test databases/configuration files are isolated. Restore points to a new directory, preserving the originals. A storage failure may leave only the last successful checkpoint; logs disclose unsaved terminal results.

Verification results are recorded after final execution in README. Tests include authorization/CSRF/session revocation, multi-client STOP, schema/backup integrity, navigation, operations, sensors, disconnect/reconnect and responsive UI. Browser QA also caught and corrected an import-order failure in the new lazy-loading development path.

Remaining limitations: shared credential (no individual accounts), no distributed sessions/rate limiting, no authentication confidentiality for anonymous monitoring, JSON-history analytics still scan records, no Pi/TLS LAN soak test, and no formal penetration test. Existing third-party AnyIO test deprecation remains. This is ready for **Phase 5B staging/deployment preparation**, conditional on the documented TLS, secrets, backup and resource checks; it is not a certified robotics safety system or hardware-ready deployment.

## Executed final verification

- Backend: `env -u PYTHONPATH backend/.venv/bin/python -m pytest backend/tests -q` — **127 passed, 0 failed**, one upstream AnyIO deprecation warning.
- Frontend: `npm run build` — **passed**; largest chart chunk about 465 kB, entry about 246 kB (minified build artifacts, not runtime benchmarks).
- Browser: `npm run test:e2e` — **15 passed, 0 failed**, including the existing Phase 1–4B regressions and new observer/login UI checks. Real TLS certificate/proxy operation is not covered by this local browser run; HTTPS session behavior is covered by isolated TestClient tests.
- `git diff --check` — passed.

New files: `backend/app/security.py`, `backend/app/backup.py`, `backend/tests/test_security.py`, `frontend/src/auth.ts`, `frontend/src/components/OperatorSession.tsx`, `frontend/tests/security.spec.ts`, and this report. Existing API/simulator/operations, hooks, UI guards, build/test configuration and README were updated in place.
