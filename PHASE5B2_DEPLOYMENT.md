# Phase 5B.2 — private-LAN HTTPS deployment

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
| `OPERATOR_PASSWORD_HASH` | Phase 5A scrypt output; no plaintext password |
| `CADDY_BIN` | Approved executable path, normally `<checkout>/.tools/caddy` |
| `LAN_STATE_DIR` | Absolute private directory for generated proxy config, CA and certificate state |
| `TLS_MODE` | `internal` or `provided` |
| `MISSION_DB_PATH`, `ROBOT_CONFIG_PATH` | Optional absolute paths to existing saved files; omit to preserve `backend/data` defaults |

For a hostname such as `amr.home.arpa`, arrange your private router/DNS to resolve that name **only to `LAN_BIND_IP`**, on the server and every client. Local server-only hosts entries do not configure mobile clients. Using the explicit private IP is simpler for initial testing. There is no automatic mDNS/DNS configuration. Prefer a DHCP reservation; changing addresses requires configuration/certificate review. IPv6 access is intentionally unsupported in this phase.

Generate a long, unique operator password interactively:

```bash
cd ~/Projects/PBL4_Dashboard/backend
env -u PYTHONPATH .venv/bin/python -m app.security
```

This prompts without echoing your password, requires at least 12 characters and prints `OPERATOR_PASSWORD_HASH=...`. Replace the one placeholder hash line in the private file with that output. Do not paste passwords/hashes into source files, frontend variables, issue reports or Git. The LAN launcher does not accept credentials as CLI arguments. A change to the hash takes effect on restart and invalidates the in-memory sessions.

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

Use the helper's documented source paths if overridden; it backs up SQLite consistently with WAL state and copies saved JSON. For a full host migration, additionally back up the private env and Caddy CA/state separately into protected storage. Treat those backups as secrets. To restore, stop all processes, keep a copy of the current files, restore a matched JSON/database snapshot to the configured paths, verify `PRAGMA integrity_check`, confirm file ownership, then start and review saved state before issuing commands. Do not copy just a running database file and discard its WAL. Never overwrite developer data for a smoke test.

### Health, access and permissions

For internal CA mode, use the public root and your configured URL:

```bash
curl --fail --show-error \
  --cacert /absolute/LAN_STATE_DIR/data/caddy/pki/authorities/local/root.crt \
  https://YOUR_CONFIGURED_LAN_HOST:8443/api/health
```

Expected: `status=ok`, `simulation=true`, `hardware_enabled=false`. `/api/auth/session` initially reports `mode=lan`, `role=observer`. No login is required to read telemetry, sensor simulation, maps, mission history or health on the allowed private network; do not store sensitive data under an expectation of per-observer authorization.

Enter the private operator password in the existing Dashboard sign-in form. Cookies are opaque, Secure, HttpOnly and SameSite=Strict. Sessions expire after eight hours and are revoked by logout/restart; operator-owned sockets close and the existing disconnect safety clears/pauses motion. Mutating HTTP requests require an authenticated session, allowed Origin and session CSRF token. WebSocket handshakes require an allowed Origin; control requires a still-valid operator session, while observers can receive read-only streams. A valid operator on a separate connection/session can STOP another owner's simulated motion. STOP does not authorize observers or bypass Host/Origin validation. Existing rate/capacity limits are retained; proxy clients cannot evade login limits by forging forwarding headers.

## Verification and troubleshooting

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

Manual acceptance still required: verified root import on actual Windows/Ubuntu/mobile browsers, cross-device HTTPS/WSS login/STOP/logout, private DNS/DHCP stability, backend-port refusal from another device, firewall/router exposure review (including no port forwarding), wireless disconnect/reconnect behavior, clock/certificate renewal checks, backup/restore drill, and long-duration load/performance testing. No claim is made that those external-device checks were automated.

## Future Raspberry Pi 4 readiness and limits

The application remains pure Python/TypeScript with no hardware imports. Python 3.10 is supported; do not source a ROS environment into this service. `env -u PYTHONPATH` isolates inherited ROS Python paths. ROS 2 Humble's presence does not enable integration. Use ARM64 Linux, an ARM64 Caddy binary and project-local ARM64 Python dependencies; this laptop's x86 venv/binary cannot be copied to the Pi.

Build assets on the Pi using Node 24, or build from the same lockfile/source elsewhere and transfer `frontend/dist` as an artifact. Node is not a runtime dependency of either production launcher. Use one backend process, with a separate Caddy process and foreground supervisor. A future systemd service, startup at boot, restart policy, privileges and firewall configuration need explicit approval and separate review.

Give the Pi a stable private address/name, provision its own protected configuration/certificates, transfer data only after SQLite-aware backup and shutdown, verify integrity and test STOP before regular use. Watch actual host CPU/RAM/storage using `ps`, `top`, `free -h` and `df -h`; the Dashboard's health charts are **simulated**, not Pi measurements. Review SD-card durability, WAL growth/backups and free space. Measure under realistic simultaneous clients before claiming Pi performance.

There was **no deployment to or access of the real Pi**. ARM64 performance, physical-network/mobile behavior, unattended operation and hardware ROS/UART/camera integration are not certified by this phase. The current localhost/private-interface tests establish software readiness for a later supervised Pi simulation deployment, not production-grade robotics safety or Internet readiness.
