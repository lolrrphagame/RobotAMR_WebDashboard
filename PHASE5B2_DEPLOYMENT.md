# Phase 5B.2 — private-LAN HTTPS · authenticated Operator/Observer

Simulation only. No ROS 2, serial, GPIO, motor, LiDAR or camera adapter is enabled by deployment. The simulator, saved data formats, ownership rules and STOP behavior are unchanged. This is a foreground, single-host deployment, not a public Internet service or a hardware safety system.

## Architecture and trust boundaries

```text
Windows / Ubuntu / mobile browser
  https://<configured-LAN-host-or-IP>:8443
  same-origin built React + /api + WSS /ws/telemetry + /ws/sensors
        |
  Caddy: TLS, explicit private IPv4 bind, private-client ACL
        | HTTP/WebSocket over loopback only; original Host/Origin
  Uvicorn 127.0.0.1:8001: APP_MODE=lan, one worker, no reload
        | Phase 5A authentication, CSRF, rate limits, ownership, watchdog
  one existing simulator + saved JSON + SQLite WAL
```

`start-dashboard.sh` remains unchanged: local mode, HTTP on loopback, no proxy-header trust, local operator behavior. **Never proxy the local-mode server onto a network.** `start-dashboard-lan.sh` always obtains `APP_MODE=lan` from an explicitly validated private file. LAN mode has no loopback operator bypass, including behind Caddy.

The shared production asset implementation serves only the built index, known Dashboard pages and approved assets inside `frontend/dist/assets`. Navigation/Missions refresh works. API docs, source maps, source files, Vite endpoints, arbitrary SPA fallback paths and secrets are not served. Caddy has no filesystem server or public admin listener. HTTP redirects, privileged ports, HTTP/3 UDP listeners and automatic trust installation are disabled.

Caddy preserves browser Host/Origin, replaces forwarded scheme/client IP, and rejects unmatched hosts with 421. FastAPI retains its own Host/Origin/TLS checks. Uvicorn trusts forwarded headers **only from 127.0.0.1**, never `*`. The loopback hop is intentionally plaintext, on the same trusted host. Other local users/processes can reach that hop and spoof proxy headers; they still receive no local operator bypass and need operator authentication. This is not isolation from a compromised host or account. Do not put another proxy/CDN/tunnel in front of this topology without a separate security review.

Only one explicit RFC1918 IPv4 bind is permitted (127/8 additionally allowed for isolated staging). `0.0.0.0`, public, link-local, multicast and IPv6 binds are refused. Proxy client addresses must be RFC1918 or loopback. Do not forward the port on a router, enable UPnP mappings, publish DNS to public addresses, or expose it through a tunnel. No firewall rules, packages, services or OS trust stores are changed by the launcher.

## Prerequisites and project-local installation

Use the README project-local Python/Node dependency instructions. Python 3.10+, a venv and Node.js 24 are required for building; Caddy and OpenSSL are needed for the new deployment/testing workflows. No OS package is installed automatically. Stop development/local servers before touching the same saved data. Build once:

```bash
cd ~/Projects/PBL4_Dashboard
source ~/.nvm/nvm.sh
nvm use 24
npm --prefix frontend ci
npm --prefix frontend run build
```

The LAN launcher serves existing `dist`; it deliberately does not rebuild during startup. Stop, rebuild and restart after frontend changes. Node/npm are not required at runtime when built assets are present.

### Caddy binary

Caddy 2.11.9 was installed into the ignored `.tools/caddy` directory with explicit user approval for this implementation. Its official archive was verified using the release's **SHA-512** checksums. There was no sudo, system package, service, firewall or trust-store installation. The binary is not committed; a new checkout needs a binary. Review/approve this installation on each new host, or supply an already approved absolute `CADDY_BIN` path. See [official installation choices](https://caddyserver.com/docs/install) and [release assets](https://github.com/caddyserver/caddy/releases/tag/v2.11.9).

Example manual user-local installation on **x86-64 Ubuntu**, after approval:

```bash
mkdir -p -m 700 .tools
curl --fail --location --proto '=https' --tlsv1.2 \
  --output .tools/caddy_2.11.9_linux_amd64.tar.gz \
  https://github.com/caddyserver/caddy/releases/download/v2.11.9/caddy_2.11.9_linux_amd64.tar.gz
curl --fail --location --proto '=https' --tlsv1.2 \
  --output .tools/caddy_2.11.9_checksums.txt \
  https://github.com/caddyserver/caddy/releases/download/v2.11.9/caddy_2.11.9_checksums.txt
(cd .tools && sha512sum --check --ignore-missing caddy_2.11.9_checksums.txt)
# Continue only if checksum verification succeeds.
tar -xzf .tools/caddy_2.11.9_linux_amd64.tar.gz -C .tools caddy
chmod 700 .tools/caddy
.tools/caddy version
```

On a future **ARM64** Pi, use the `linux_arm64.tar.gz` asset and corresponding checksum entry instead. Select an explicitly reviewed release when upgrading; do not replace a running binary. Missing Caddy causes a clear startup error; the launcher never downloads it.

## Private configuration and password

Configuration is **dotenv data**, not a shell script. It is not sourced and `${...}` is not expanded. Unknown keys are errors. The file must be an owned, regular, non-symlink file with mode 600, outside this repository. The proxy state directory must also be outside the repository, owned, mode 700, non-symlink. Keep that parent directory private and trusted.

For a new setup (do not overwrite an existing private configuration):

```bash
cd ~/Projects/PBL4_Dashboard
mkdir -p -m 700 "$HOME/.config/pbl4"
(umask 077; cp -n deployment/lan.env.example "$HOME/.config/pbl4/lan.env")
chmod 600 "$HOME/.config/pbl4/lan.env"
ip -brief -4 address
```

Edit `~/.config/pbl4/lan.env` privately. The supplied `192.168.1.100` and `YOUR_USER` are **placeholders**, not detected addresses. Set:

| Key | Required meaning |
| --- | --- |
| `APP_MODE` | Exactly `lan` |
| `LAN_HOST` | One lowercase private DNS name or the server's explicit private IPv4 address |
| `LAN_BIND_IP` | The server's actual RFC1918 IPv4 interface address |
| `HTTPS_PORT` | Default 8443, permitted range 1024–65535 |
| `BACKEND_PORT` | Default 8001; a different non-privileged port, always bound to 127.0.0.1 |
| `ALLOWED_HOSTS` | Exactly `LAN_HOST`, without a port, no aliases/wildcards |
| `ALLOWED_ORIGINS` | Exactly `https://LAN_HOST:HTTPS_PORT`, no trailing slash |
| `ACCOUNT_STORE_PATH` | Required absolute private account JSON path outside the repository, mode 600 |
| `OPERATOR_PASSWORD_HASH` | Optional preserved legacy hash for explicit migration only; ignored for account login |
| `CADDY_BIN` | Approved executable path, normally `<checkout>/.tools/caddy` |
| `LAN_STATE_DIR` | Absolute private directory for generated proxy config, CA and certificate state |
| `TLS_MODE` | `internal` or `provided` |
| `MISSION_DB_PATH`, `ROBOT_CONFIG_PATH` | Optional absolute paths to existing saved files; omit to preserve `backend/data` defaults |

For a hostname such as `amr.home.arpa`, arrange your private router/DNS to resolve that name **only to `LAN_BIND_IP`**, on the server and every client. Local server-only hosts entries do not configure mobile clients. Using the explicit private IP is simpler for initial testing. There is no automatic mDNS/DNS configuration. Prefer a DHCP reservation; changing addresses requires configuration/certificate review. IPv6 access is intentionally unsupported in this phase.

### First Operator and additional users

Accounts represent people, not IP addresses. Provision them on the trusted Ubuntu host using the administrator CLI; there is no public registration or account-administration endpoint. Passwords are entered twice using a non-echoing interactive prompt and never passed on the command line. Usernames contain 1–64 letters, digits, dots, underscores or hyphens and are case-insensitive (stored lowercase). Roles are `operator` and `observer`; account capacity is 128.

For a **new** deployment:

```bash
cd ~/Projects/PBL4_Dashboard/backend
env -u PYTHONPATH .venv/bin/python -m app.accounts --store "$HOME/.config/pbl4/accounts.json" create alice --role operator
env -u PYTHONPATH .venv/bin/python -m app.accounts --store "$HOME/.config/pbl4/accounts.json" create viewer --role observer
```

Add `ACCOUNT_STORE_PATH=/home/YOUR_USER/.config/pbl4/accounts.json` to your private LAN env using the actual absolute path. The CLI creates the account file atomically with mode 600 and uses an advisory lock for concurrent administrator edits. The launcher requires an existing valid store and does not silently create accounts. Accounts/secrets may not be stored inside the repository, frontend assets or environment variables prefixed with `VITE_`.

New/reset hashes use salted scrypt N=32768, r=8, p=3, a 32 MiB work factor from [OWASP's supported scrypt settings](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#scrypt). Password length is 12–256 characters. No plaintext passwords are stored. Private JSON includes hashes, roles, enabled flags and random revision identifiers; it contains no session tokens. Keep the containing directory private. The API never returns hashes or other users' account records.

### Migration from the previous shared Operator password

Back up the existing private env first. Do **not** remove or replace `OPERATOR_PASSWORD_HASH`. Import that exact existing hash into an explicitly named Operator account:

```bash
cd ~/Projects/PBL4_Dashboard/backend
env -u PYTHONPATH .venv/bin/python -m app.accounts --store "$HOME/.config/pbl4/accounts.json" migrate-legacy operator --config "$HOME/.config/pbl4/lan.env"
```

If the old hash is in `operator.env`, supply that private file instead. The command reads but never modifies the old file, imports its hash unchanged and refuses to overwrite an existing username. The existing password now works with username `operator`. Add `ACCOUNT_STORE_PATH` to the LAN env; retain its old hash line for backup/migration records. The old environment hash **does not enable a fallback account**. Missing account configuration fails closed with migration guidance. Never test a migration against developer secrets or replace existing accounts during automated tests.

Imported legacy scrypt hashes keep their original work factor for compatibility. After confirming account access, an explicit `reset-password` upgrades that account to the stronger new settings. This requires an administrator choosing a new password; no credential is silently deleted or changed. A backend restart requires all users to log in again and never resumes motion.

### Disable, reset, change role and revoke

Run from `backend/` (all commands preserve other users and simulator data):

```bash
env -u PYTHONPATH .venv/bin/python -m app.accounts --store "$HOME/.config/pbl4/accounts.json" list
env -u PYTHONPATH .venv/bin/python -m app.accounts --store "$HOME/.config/pbl4/accounts.json" disable viewer
env -u PYTHONPATH .venv/bin/python -m app.accounts --store "$HOME/.config/pbl4/accounts.json" enable viewer
env -u PYTHONPATH .venv/bin/python -m app.accounts --store "$HOME/.config/pbl4/accounts.json" reset-password alice
env -u PYTHONPATH .venv/bin/python -m app.accounts --store "$HOME/.config/pbl4/accounts.json" set-role viewer observer
env -u PYTHONPATH .venv/bin/python -m app.accounts --store "$HOME/.config/pbl4/accounts.json" revoke alice
```

`list` prints only username/role/enabled state. Reset prompts interactively. Disable, enable, password reset, role change and revoke rotate that user's revision; active sessions lose access without restarting the service. Read/command requests check the account on each use; open telemetry and sensor streams recheck before publishing (approximately 0.1/0.2 seconds). Existing owner-disconnect logic stops manual motion or pauses navigation/operations. Revocation does not automatically resume anything. Re-enabling a user requires a fresh login. Other users' sessions remain valid.

Only the trusted host administrator can run this CLI through filesystem access. An Operator's dashboard privileges do not imply account-administration rights. If every Operator is disabled, recover through this CLI; there is no anonymous recovery endpoint. No account deletion command is provided.

Do not `source` this file into a shell. The launcher intentionally ignores inherited security/data settings and uses only the validated file, with saved-data defaults when the optional paths are omitted.

## TLS certificates and safe client trust

### Internal CA (default)

Use `TLS_MODE=internal`. Caddy creates and renews a leaf certificate for the configured host/IP under the private `LAN_STATE_DIR`. The CA must remain stable across restarts. The public trust anchor is:

```text
<LAN_STATE_DIR>/data/caddy/pki/authorities/local/root.crt
```

The launcher prints this path. `skip_install_trust` prevents automatic modification of Ubuntu, Firefox or Java trust stores ([Caddy options](https://caddyserver.com/docs/caddyfile/options#skip-install-trust)). Transfer **only `root.crt`** to clients over a channel you trust, such as a known USB drive. Never transfer `root.key`, intermediate keys, server keys, the whole runtime directory or the private env file. Confirm the root fingerprint against the Ubuntu terminal over a separate trusted channel:

```bash
openssl x509 -in /absolute/LAN_STATE_DIR/data/caddy/pki/authorities/local/root.crt \
  -noout -subject -fingerprint -sha256
```

Trusting this CA permits it to authenticate other sites, so protect its keys and remove the trust from clients when retiring the deployment. Do not regenerate/delete the CA directory as routine troubleshooting; clients would need to verify and trust a new root.

### Your own trusted certificate

Set `TLS_MODE=provided`, `TLS_CERT_FILE=/absolute/private/fullchain.pem`, and `TLS_KEY_FILE=/absolute/private/key.pem`. Both files must be owned, mode 600, outside the repository, and non-symlinks. The certificate must have the exact hostname/IP in its SAN, be within its validity period, and chain to a CA trusted by all clients. Caddy validates loading/key matching before the simulator starts. Client TLS validation additionally checks identity, validity and trust. These supplied files are **not renewed automatically**; renew them and restart gracefully. Certificates from a private organizational CA still require that organization's approved trust process.

### Windows, Ubuntu and mobile

First verify the root fingerprint, then explicitly install trust on the intended client. This is a manual user/administrator decision; nothing in the launcher performs it.

- **Windows:** use `certmgr.msc`, Current User → Trusted Root Certification Authorities → Certificates → Import, and select the verified public root certificate. Edge/Chrome should trust it for that user. Firefox may use a separate Authorities store. Follow [Microsoft certificate-store guidance](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/trusted-root-certification-authorities-certificate-store). Do not import a private key or an unverified certificate.
- **Ubuntu:** use the browser's certificate manager to import the verified root as a trusted website authority in the chosen user profile. Firefox's Authorities import is described in [Caddy's operating guide](https://caddyserver.com/docs/running). System-wide trust installation is optional and requires a separate administrator decision; no sudo steps are needed for this project's launcher.
- **iOS/iPadOS:** install the verified CA profile, then enable trust under Settings → General → About → Certificate Trust Settings, as described by [Apple](https://support.apple.com/en-us/102390). Full trust is a deliberate separate step.
- **Android:** install the verified CA using Security & privacy → More security settings → Encryption & credentials → Install a certificate → CA certificate, where available. Names vary by OS/vendor; see [Google's certificate instructions](https://support.google.com/pixelphone/answer/2844832?hl=en). Managed devices/browsers may disallow user CAs; use administrator-approved trust instead.

After trust is installed, open **`https://<configured-host-or-IP>:8443`** from the same private network. A certificate warning means trust, name, chain, validity or device clock is wrong. Fix it; **never bypass browser warnings, use `curl -k`, disable TLS validation, or add ignore-certificate flags**. No port-80 HTTP redirect is provided. A dual-boot laptop stops hosting Ubuntu when booted into Windows; use a separate device now, and the future independent Raspberry Pi host later.

## Startup, operations and backups

Validate without opening listeners or application data:

```bash
cd ~/Projects/PBL4_Dashboard
./start-dashboard-lan.sh --config "$HOME/.config/pbl4/lan.env" --check
```

Start (default configuration path is already `~/.config/pbl4/lan.env`):

```bash
./start-dashboard-lan.sh
# Or an explicit private file:
./start-dashboard-lan.sh --config /absolute/private/lan.env
```

It validates the private config and production build, validates Caddy TLS configuration, acquires the **same SQLite production lock as the local launcher**, pre-binds FastAPI to loopback, starts one backend, checks its health, and starts the HTTPS proxy. The URL and supervisor PID are printed after the TLS listener opens. An occupied address, invalid configuration, failed certificate load, database failure or child exit gives an error and shuts down any children already started. No hidden daemon, reload process, extra simulator worker, service or automatic mission execution is introduced.

Keep this terminal attached. Stop with **Ctrl+C**, or `kill -TERM <printed-supervisor-pid>`. The supervisor stops Caddy first, then signals Uvicorn and waits for its existing lifespan to halt motion and close SQLite. Wait for `Application shutdown complete` before restarting. Send the signal to the supervisor, not just a child. Forced SIGKILL, power loss or killing the terminal/process group cannot guarantee graceful shutdown; existing SQLite recovery/interruption behavior still applies. The launcher has a bounded shutdown wait and reports a forced child exit if necessary.

The advisory database lock prevents simultaneous LOCAL/LAN production launchers using the same database. Development Uvicorn does not take this lock: **stop development first**. Never share a live SQLite file between hosts or independent simulators. On restart, Home/waypoints/templates/pending jobs/history are retained; pose starts at saved valid Home, motion is stopped, unfinished missions are interrupted, and no mission auto-resumes. Sessions are in memory and require login after restart.

Before changing hosts/configuration, use the existing SQLite-aware backup helper and a new private destination:

```bash
cd ~/Projects/PBL4_Dashboard/backend
env -u PYTHONPATH .venv/bin/python -m app.backup --help
```

Use the helper's documented source paths if overridden; it backs up SQLite consistently with WAL state and copies saved JSON. For a full host migration, additionally back up the private env, **account JSON** and Caddy CA/state separately into protected storage. The account file is replaced atomically; a private file copy is a complete revision, but coordinate administrator edits during backup. The simulator backup helper does not include accounts or TLS keys. Preserve mode 600 on the account file and mode 700 on secret directories; never export them with dashboard CSVs. Restore accounts only with the backend stopped so old in-memory sessions cannot survive a restored revision. Treat those backups as secrets. To restore, stop all processes, keep a copy of the current files, restore a matched JSON/database snapshot to the configured paths, verify `PRAGMA integrity_check`, confirm file ownership, then start and review saved state before issuing commands. Do not copy just a running database file and discard its WAL. Never overwrite developer data for a smoke test.

### Health, access and permissions

For internal CA mode, use the public root and your configured URL:

```bash
curl --fail --show-error \
  --cacert /absolute/LAN_STATE_DIR/data/caddy/pki/authorities/local/root.crt \
  https://YOUR_CONFIGURED_LAN_HOST:8443/api/health
```

Expected: `status=ok`, `simulation=true`, `hardware_enabled=false`. Anonymous `/api/auth/session` reports `mode=lan`, `authenticated=false`, `role=null`, `username=null`, and an empty CSRF token. This minimal endpoint and health remain public infrastructure endpoints; neither exposes robot state.

**All LAN users must authenticate.** Anonymous visitors receive only the login page and required static assets. Requests for robot state, map, configuration, events, diagnostics, sensor data, mission queue/history/analytics and any future non-public endpoint return 401. Both WebSockets reject unauthenticated handshakes before sending a frame. Static HTML for known SPA routes contains no private telemetry and displays the dedicated login screen until authentication succeeds.

Sign in using the individually provisioned username/password over trusted HTTPS from Windows, Ubuntu or mobile. The header shows the authenticated username and either **Authorized operator** or **Read-only observer**, with Sign out for both roles. No dashboard view is mounted behind the login form.

| Identity | Monitoring / read-only sockets | Mutations / motion / mission control / STOP | Account administration |
| --- | --- | --- | --- |
| Anonymous | Denied (401 / rejected handshake) | Denied (401) | Denied |
| Authenticated Observer | Allowed | Denied (403 / socket control rejected) | Denied |
| Authenticated Operator | Allowed | Allowed with session/CSRF/ownership checks | Host-administrator CLI only |

Observers can view all monitoring pages and history. Manual controls, Home/waypoint/settings changes, queue editing/execution and STOP are disabled for Observers in the UI and independently denied by the backend. The server takes roles from the private store, never a browser-supplied role. One Operator owns motion at a time; a second independently authenticated Operator may STOP that owner. STOP remains an application simulation control, not a physical emergency stop.

Cookies remain opaque, Secure, HttpOnly and SameSite=Strict. Sessions expire after eight hours and are revoked by logout/restart or an account revision change. Both roles' sensitive sockets close on expiration/revocation, and any owner is stopped/paused through the original disconnect logic. HTTP mutations, including Observer logout, require an allowed Origin and the session CSRF token. Login requires an allowed Origin. Session status returns only the requesting user's username/role/CSRF, never a token or account list.

The frontend authentication boundary unmounts all private components, closes sockets and clears private in-memory view state on sign-out/authentication loss, so cached telemetry is not shown behind the login screen. Sensitive HTTP responses remain `Cache-Control: no-store`. A restored browser page revalidates its session before mounting private views. There is no automatic motion resume. When a network failure prevents confirmation of server logout, the browser still clears its private UI and reports the failed revocation; reconnect and sign in to complete logout, or use the host CLI to revoke that account's sessions.


## Verification and troubleshooting

Security Option B verification on 2026-11-21: baseline 160 backend tests passed with one opt-in network skip. Final verification passed **190 backend tests**, including the opt-in same-laptop private-interface test; **16 development**, **3 local-production**, and **4 trusted-HTTPS LAN Playwright tests**, plus the production build. No final test failures/skips in the opt-in backend run. Without a configured private-interface address the backend suite reports 189 passed / one explicit skip. Existing AnyIO deprecation and Vite empty-`react`-chunk notices remain. These results do not certify remote-device trust, firewall/router behavior or Pi performance.

Automated tests use temporary certificates, configuration and databases, never the user's saved records. Run from the repository:

```bash
env -u PYTHONPATH backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run build
npm --prefix frontend run test:e2e
npm --prefix frontend run test:production
npm --prefix frontend run test:lan
```

Real Caddy integration tests skip explicitly if the approved `.tools/caddy` binary is absent. LAN browser tests require it, OpenSSL, Chromium >=146 and the already installed NSS library; they fail clearly if prerequisites are missing. They create a temporary CA, trust it in an isolated Chromium NSS database under a temporary `XDG_DATA_HOME`, and delete the test data after shutdown. They **do not modify user/system trust** and keep certificate verification enabled. They exercise a supplied certificate; backend tests exercise Caddy's internal CA. See [Chromium NSS database behavior](https://chromium.googlesource.com/chromium/src.git/+/master/docs/linux/cert_management.md). Test ports 18443/18001 (LAN browser), 18173 (production), and 15173/18000 (development) must be free.

An optional private-interface staging test is opt-in to avoid opening a network listener during normal tests. Set the actual laptop address discovered with `ip -brief -4 address`:

```bash
PBL4_LAN_TEST_IP=YOUR_PRIVATE_IPV4 env -u PYTHONPATH \
  backend/.venv/bin/python -m pytest backend/tests -q
```

This uses random ephemeral credentials and temporary saved files, verifies trusted HTTPS/WSS through the laptop's private interface, and confirms the backend port is unreachable through that interface. It stops everything after the test. A same-machine private-interface check is **not** verification from Windows/mobile or through a router/firewall.

| Symptom | Check |
| --- | --- |
| Config missing, permissions rejected | Correct absolute external path, owner, mode 600; private runtime directory mode 700; no symlinks |
| Host does not resolve / mismatch | Private DNS or exact IPv4, matching `LAN_BIND_IP`, host/origin and port; no alternate hostname browsing |
| Address unavailable/in use | Correct current interface, free ports; stop only the intended existing process |
| Caddy/build missing | Install approved user-local Caddy / build existing frontend; nothing is downloaded by startup |
| TLS certificate warning | Verify root fingerprint/trust, exact SAN, full chain, certificate dates and client/server clocks |
| Browser cannot reach HTTPS | Same LAN, correct HTTPS port, guest Wi-Fi/client isolation/VPN routing, existing firewall policy; no automatic firewall changes |
| HTTP 400/403/421 | Check exact Host/Origin, HTTPS scheme and proxy topology; never weaken allowlists to `*` |
| Read-only / HTTP 401 | Sign in; expired/revoked/restarted sessions must log in again |
| HTTP 403 on mutation | Allowed Origin plus matching session CSRF; use the normal UI or an authenticated API client |
| HTTP 429 | Existing login/control limits; retry after the window, do not rotate spoofed IP headers |
| WebSocket disconnected | Browser developer Network WS should show `wss://<same-host>:<same-port>/ws/...`, successful 101 and valid cookies/Origin; inspect Caddy/backend logs and TLS trust; no hardcoded ws:// dev URLs |
| SQLite lock/startup error | Stop the intended local/LAN/dev simulator; preserve data, inspect permissions/storage and use verified backups |

Upstream keepalive is disabled on the loopback proxy hop because reconnect stress testing exposed stale connection reuse with the tested Caddy/Uvicorn combination. Dial/header waits are bounded. This does not disable browser HTTPS keepalive or established WSS streams; it trades small per-request local connection overhead for reliable upgrades.

Manual acceptance still required: verified root import on actual Windows/Ubuntu/mobile browsers, cross-device HTTPS/WSS Operator and Observer login/logout, Observer denial of STOP, independent-Operator STOP, live account disable/revoke, private DNS/DHCP stability, backend-port refusal from another device, firewall/router exposure review (including no port forwarding), wireless disconnect/reconnect behavior, clock/certificate renewal checks, backup/restore drill, and long-duration load/performance testing. No claim is made that those external-device checks were automated.

## Future Raspberry Pi 4 readiness and limits

The application remains pure Python/TypeScript with no hardware imports. Python 3.10 is supported; do not source a ROS environment into this service. `env -u PYTHONPATH` isolates inherited ROS Python paths. ROS 2 Humble's presence does not enable integration. Use ARM64 Linux, an ARM64 Caddy binary and project-local ARM64 Python dependencies; this laptop's x86 venv/binary cannot be copied to the Pi.

Build assets on the Pi using Node 24, or build from the same lockfile/source elsewhere and transfer `frontend/dist` as an artifact. Node is not a runtime dependency of either production launcher. Use one backend process, with a separate Caddy process and foreground supervisor. A future systemd service, startup at boot, restart policy, privileges and firewall configuration need explicit approval and separate review.

Give the Pi a stable private address/name, provision its own protected configuration/certificates, transfer data only after SQLite-aware backup and shutdown, verify integrity and test STOP before regular use. Watch actual host CPU/RAM/storage using `ps`, `top`, `free -h` and `df -h`; the Dashboard's health charts are **simulated**, not Pi measurements. Review SD-card durability, WAL growth/backups and free space. Measure under realistic simultaneous clients before claiming Pi performance.

There was **no deployment to or access of the real Pi**. ARM64 performance, physical-network/mobile behavior, unattended operation and hardware ROS/UART/camera integration are not certified by this phase. The current localhost/private-interface tests establish software readiness for a later supervised Pi simulation deployment, not production-grade robotics safety or Internet readiness.

## Isolated manual role staging

To verify the two login roles before opening a private interface, prepare a separate private env with `LAN_HOST=127.0.0.1`, `LAN_BIND_IP=127.0.0.1`, `ALLOWED_HOSTS=127.0.0.1`, and `ALLOWED_ORIGINS=https://127.0.0.1:8443`. Give it **separate absolute temporary** account, robot JSON, mission SQLite and proxy-state paths. Create temporary Operator/Observer accounts using the CLI, build the frontend, then run `./start-dashboard-lan.sh --config /absolute/private/staging.env`. Verify/trust its temporary public root in a test browser profile; do not weaken TLS. This uses real LAN-mode authorization on loopback without opening a private-network listener. Do not copy over or point staging at existing saved data. Stop the supervisor before removing staging files or test-profile trust.

Check: anonymous navigation displays only login; Observer sees telemetry/maps/history but every control and STOP is unavailable; Operator controls work; page refresh preserves a valid login; logout or CLI disable/revoke clears all private views and closes streams; owner revocation halts/pauses simulated motion; reconnect/restart never resumes it. Review the exact host/origin again before switching to the real private interface. Cross-device trust and network verification remain manual.
