"""Fixed loopback, one-worker server. No reload, proxy trust, or LAN flags."""
import os
import socket
import fcntl
import tempfile
from pathlib import Path
import uvicorn


def main():
    if os.getenv('APP_MODE', 'local') != 'local':
        raise SystemExit('ERROR: APP_MODE must be local. LAN deployment is disabled in Phase 5B.1.')
    try:
        port = int(os.getenv('DASHBOARD_PORT', '8000'))
        if not 1024 <= port <= 65535: raise ValueError()
    except ValueError:
        raise SystemExit('ERROR: DASHBOARD_PORT must be an integer from 1024 to 65535.')
    os.environ['APP_MODE'] = 'local'
    # Do not inherit permissive development/LAN origins. This launcher owns its one origin.
    os.environ['ALLOWED_HOSTS'] = '127.0.0.1,localhost'
    os.environ['ALLOWED_ORIGINS'] = f'http://127.0.0.1:{port},http://localhost:{port}'
    from .production import create_app
    try:create_app()  # Validate before opening the robot/database lifespan.
    except ValueError as exc:raise SystemExit(f'ERROR: {exc}') from exc
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind(('127.0.0.1', port))
        listener.listen(128)
    except OSError as exc:
        listener.close()
        raise SystemExit(f'ERROR: cannot bind 127.0.0.1:{port}: {exc}. Stop the existing server or select DASHBOARD_PORT.') from exc
    database = os.getenv('MISSION_DB_PATH', str(Path(__file__).resolve().parents[1] / 'data' / 'missions.sqlite3'))
    lock_path = (Path(tempfile.gettempdir()) / f'pbl4-{os.getuid()}-memory-{port}.lock' if database == ':memory:'
                 else Path(database).resolve().with_suffix(Path(database).suffix + '.production.lock'))
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = lock_path.open('a')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        listener.close()
        raise SystemExit(f'ERROR: cannot acquire production database lock {lock_path}: {exc}. Another dashboard may be running.') from exc
    print(f'PBL4 local production dashboard: http://127.0.0.1:{port}', flush=True)
    print('SIMULATION ONLY · one worker · Ctrl+C / SIGTERM for graceful shutdown', flush=True)
    config = uvicorn.Config('app.production:create_app', factory=True, host='127.0.0.1', port=port,
                            workers=1, reload=False, proxy_headers=False, ws_max_size=4096,
                            ws_ping_interval=20, ws_ping_timeout=20, timeout_graceful_shutdown=10)
    try:
        server = uvicorn.Server(config)
        server.run(sockets=[listener])
        if not server.started:raise SystemExit('ERROR: dashboard startup failed; check application/database errors above.')
    finally:
        listener.close()
        lock.close()


if __name__ == '__main__':
    main()
