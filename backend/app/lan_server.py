"""Foreground supervisor: one loopback backend and one private-LAN TLS proxy."""
import argparse
import fcntl
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import uvicorn
from .lan_config import LanConfig, ROOT


def run_backend():
    # Only the parent supplies this private socket and validated environment.
    descriptor = int(os.environ['PBL4_LAN_SOCKET_FD'])
    listener = socket.socket(fileno=descriptor)
    try:
        config = uvicorn.Config('app.production:create_lan_app', factory=True,
                                host='127.0.0.1', port=listener.getsockname()[1], workers=1, reload=False,
                                proxy_headers=True, forwarded_allow_ips='127.0.0.1',
                                ws_max_size=4096, ws_ping_interval=20, ws_ping_timeout=20,
                                timeout_graceful_shutdown=10)
        server = uvicorn.Server(config)
        server.run(sockets=[listener])
        if not server.started:
            raise SystemExit('ERROR: LAN backend startup failed; inspect application/database errors above.')
    finally:
        listener.close()


def stop_child(child):
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=15)
    except subprocess.TimeoutExpired:
        print('ERROR: child shutdown timed out; forcing exit. Check SQLite integrity before restart.', file=sys.stderr)
        child.kill()
        child.wait()


def serve(config):
    config.state.mkdir(mode=0o700, parents=True, exist_ok=True)
    filename = config.state / 'Caddyfile'
    # Prevent following an old symlink or exposing configuration while writing.
    descriptor = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(config.caddyfile())
    proxy_env = {k: v for k, v in os.environ.items() if k not in ('OPERATOR_PASSWORD_HASH', 'PYTHONPATH')}
    proxy_env.update({'XDG_DATA_HOME': str(config.state / 'data'), 'XDG_CONFIG_HOME': str(config.state / 'config')})
    subprocess.run([config.caddy, 'validate', '--config', str(filename), '--adapter', 'caddyfile'],
                   env=proxy_env, check=True, timeout=30)
    env = config.backend_environment()
    database = Path(env.get('MISSION_DB_PATH', str(ROOT / 'backend/data/missions.sqlite3'))).resolve()
    lock_path = database.with_suffix(database.suffix + '.production.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_path.open('a')
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    backend = proxy = None
    stopping = False

    def shutdown(signum, frame):
        nonlocal stopping
        stopping = True

    old_handlers = {}
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('Cannot acquire production database lock; another local or LAN dashboard may be running') from exc
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', config.backend_port))
        listener.listen(128)
        # Reserve/check the exact private bind before starting a robot lifespan.
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((config.bind, config.https_port))
        env['PBL4_LAN_SOCKET_FD'] = str(listener.fileno())
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_handlers[sig] = signal.signal(sig, shutdown)
        backend = subprocess.Popen([sys.executable, '-m', 'app.lan_server', '--backend'], cwd=ROOT / 'backend',
                                   env=env, pass_fds=(listener.fileno(),), start_new_session=True)
        # Do not expose TLS until startup/lifespan has succeeded.
        import httpx
        with httpx.Client(trust_env=False, timeout=1) as client:
            for _ in range(200):
                if stopping:
                    return
                if backend.poll() is not None:
                    raise ValueError('LAN backend exited during startup; inspect errors above')
                try:
                    response = client.get(f'http://127.0.0.1:{config.backend_port}/api/health',
                                          headers={'Host': f'{config.host}:{config.https_port}', 'X-Forwarded-Proto': 'https'})
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.05)
            else:
                raise ValueError('Timed out waiting for LAN backend health')
        proxy = subprocess.Popen([config.caddy, 'run', '--config', str(filename), '--adapter', 'caddyfile'],
                                 env=proxy_env, start_new_session=True)
        # Print readiness only after the TLS socket is listening. Trust is verified by clients.
        for _ in range(200):
            if stopping:
                return
            if proxy.poll() is not None:
                raise ValueError('Caddy exited during startup; inspect TLS/configuration errors above')
            try:
                with socket.create_connection((config.bind, config.https_port), timeout=.2):
                    break
            except OSError:
                time.sleep(.05)
        else:
            raise ValueError('Timed out waiting for Caddy HTTPS listener')
        print(f'PBL4 HTTPS LAN dashboard: {config.origin}', flush=True)
        print(f'SIMULATION ONLY · supervisor PID {os.getpid()} · backend 127.0.0.1:{config.backend_port} · one worker', flush=True)
        print('Ctrl+C / SIGTERM to this supervisor stops proxy then backend and closes SQLite.', flush=True)
        if config.values.get('TLS_MODE', 'internal') == 'internal':
            print(f'Public CA certificate (trust manually): {config.state}/data/caddy/pki/authorities/local/root.crt', flush=True)
        while not stopping:
            if backend.poll() is not None or proxy.poll() is not None:
                raise ValueError('A deployment child exited unexpectedly; shutting down both processes')
            time.sleep(.1)
    finally:
        # Stop accepting clients first; disconnect cleanup then backend lifespan flushes SQLite.
        stop_child(proxy)
        stop_child(backend)
        listener.close()
        lock.close()
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description='Separate HTTPS LAN launcher; never installs packages or changes trust/firewalls.')
    parser.add_argument('--config', default=str(Path.home() / '.config/pbl4/lan.env'))
    parser.add_argument('--check', action='store_true', help='validate private config without opening application data or network listeners')
    parser.add_argument('--backend', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.backend:
        run_backend()
        return
    try:
        config = LanConfig.load(args.config)
        if args.check:
            print(f'Valid LAN configuration: {config.origin}. No listeners started; no application data opened.')
            return
        serve(config)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f'ERROR: {exc}') from exc


if __name__ == '__main__':
    main()
