"""Real HTTPS/WSS proxy tests. All records, certificates and secrets are temporary."""
import json
import os
from pathlib import Path
import signal
import secrets
import socket
import sqlite3
import ssl
import subprocess
import time
import httpx
import pytest
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect
from app.lan_config import LanConfig, ROOT, private_ipv4
from app.production import create_app, create_lan_app
from app.security import password_hash
from app.accounts import AccountStore

PASSWORD = 'isolated-test-password-only'
CADDY = ROOT / '.tools/caddy'


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def config_file(tmp_path, **overrides):
    account_path=tmp_path/'accounts.json'
    if not account_path.exists():
        store=AccountStore(account_path)
        store.create('operator','operator',password_hash(PASSWORD))
        store.create('observer','observer',password_hash(PASSWORD))
    values = {'APP_MODE': 'lan', 'LAN_HOST': '127.0.0.1', 'LAN_BIND_IP': '127.0.0.1',
              'HTTPS_PORT': '18443', 'BACKEND_PORT': '18001', 'ALLOWED_HOSTS': '127.0.0.1',
              'ALLOWED_ORIGINS': 'https://127.0.0.1:18443', 'OPERATOR_PASSWORD_HASH': password_hash(PASSWORD),
              'CADDY_BIN': str(CADDY), 'LAN_STATE_DIR': str(tmp_path / 'runtime'), 'ACCOUNT_STORE_PATH':str(account_path),
              'MISSION_DB_PATH': str(tmp_path / 'missions.sqlite3'), 'ROBOT_CONFIG_PATH': str(tmp_path / 'robot-config.json')}
    values.update(overrides)
    path = tmp_path / 'lan.env'
    path.write_text('\n'.join(k + '=' + v for k, v in values.items()) + '\n')
    path.chmod(0o600)
    return path


@pytest.mark.parametrize('address', ['0.0.0.0', '8.8.8.8', '169.254.1.1', '224.0.0.1', '::1', '192.0.2.1'])
def test_lan_rejects_non_private_bind_addresses(address):
    with pytest.raises(ValueError):
        private_ipv4(address)


@pytest.mark.parametrize('overrides,reason', [
    ({'APP_MODE': 'local'}, 'APP_MODE=lan'),
    ({'LAN_HOST': '*'}, 'LAN_HOST'),
    ({'LAN_BIND_IP': '0.0.0.0'}, 'RFC1918'),
    ({'ALLOWED_HOSTS': '*'}, 'ALLOWED_HOSTS'),
    ({'ALLOWED_ORIGINS': 'http://127.0.0.1:18443'}, 'ALLOWED_ORIGINS'),
    ({'HTTPS_PORT': '443'}, 'HTTPS_PORT'),
    ({'BACKEND_PORT': '18443'}, 'must differ'),
    ({'ACCOUNT_STORE_PATH': str(ROOT/'accounts.json')}, 'outside the repository'),
    ({'TLS_MODE': 'insecure'}, 'TLS_MODE'),
    ({'TLS_MODE': 'provided'}, 'TLS_CERT_FILE'),
    ({'MISSION_DB_PATH': ':memory:'}, 'persistent path'),
    ({'LAN_STATE_DIR': str(ROOT / 'private-runtime')}, 'outside the repository'),
    ({'CADDY_BIN': '/missing/caddy'}, 'Caddy not found'),
    ({'UNRECOGNIZED': 'true'}, 'Unknown private config'),
])
def test_lan_configuration_fails_closed(tmp_path, overrides, reason):
    with pytest.raises(ValueError, match=reason):
        LanConfig.load(config_file(tmp_path, **overrides))
    assert not (tmp_path / 'missions.sqlite3').exists()


def test_private_configuration_permissions_and_symlinks(tmp_path):
    path = config_file(tmp_path)
    path.chmod(0o644)
    with pytest.raises(ValueError, match='chmod 600'):
        LanConfig.load(path)
    path.chmod(0o600)
    link = tmp_path / 'linked.env'
    link.symlink_to(path)
    with pytest.raises(ValueError, match='no symlinks'):
        LanConfig.load(link)


def test_lan_factory_never_enables_local_operator_bypass(monkeypatch):
    with pytest.raises(ValueError, match='APP_MODE=lan'):
        create_lan_app()
    monkeypatch.setenv('APP_MODE', 'lan')
    with pytest.raises(ValueError, match='loopback-only'):
        create_app()
    with pytest.raises(ValueError, match='LAN requires'):
        create_lan_app()


def test_proxy_config_does_not_trust_client_forwarded_headers(tmp_path, monkeypatch):
    # A harmless executable suffices for pure configuration tests.
    path = config_file(tmp_path, CADDY_BIN='/bin/true')
    config = LanConfig.load(path)
    content = config.caddyfile()
    assert 'bind 127.0.0.1' in content and 'reverse_proxy 127.0.0.1:18001' in content
    assert 'header_up X-Forwarded-For {http.request.remote.host}' in content
    assert 'header_up X-Forwarded-Proto https' in content
    assert 'admin off' in content and 'skip_install_trust' in content and 'protocols h1 h2' in content
    assert config.values['OPERATOR_PASSWORD_HASH'] not in content
    monkeypatch.setenv('ALLOWED_HOSTS', '*')
    monkeypatch.setenv('ROBOT_CONFIG_PATH', '/unwanted/path')
    env = config.backend_environment()
    assert env['ALLOWED_HOSTS'] == '127.0.0.1'
    assert env['ROBOT_CONFIG_PATH'] == str(tmp_path / 'robot-config.json')
    assert 'PYTHONPATH' not in env


def receive_until(ws, predicate):
    for _ in range(100):
        frame = json.loads(ws.recv(timeout=3))
        if predicate(frame):
            return frame
    raise AssertionError('Expected WebSocket response did not arrive')


def launch(path, config, tmp_path):
    log = (tmp_path / f'lan-{time.monotonic_ns()}.log').open('w+')
    process = subprocess.Popen([str(ROOT / 'start-dashboard-lan.sh'), '--config', str(path)], cwd=ROOT,
                               stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    cert = config.values.get('TLS_CERT_FILE')
    context = ssl.create_default_context(cafile=cert) if cert else None
    # Internal mode creates a CA. Wait for it, then verify TLS against that CA (never bypass TLS).
    ca = config.state / 'data/caddy/pki/authorities/local/root.crt'
    client = None
    for _ in range(240):
        if process.poll() is not None:
            break
        if context is None and ca.is_file():
            context = ssl.create_default_context(cafile=str(ca))
        if context is not None:
            if client is None:
                client = httpx.Client(base_url=config.origin, verify=context, trust_env=False, timeout=1)
            try:
                if client.get('/api/health').status_code == 200 and 'PBL4 HTTPS LAN dashboard:' in Path(log.name).read_text():
                    return process, client, log, context
            except httpx.HTTPError:
                pass
        time.sleep(.05)
    stop(process, client, log, require_clean=False)
    raise AssertionError('HTTPS LAN startup failed: ' + (tmp_path / log.name).read_text())


def stop(process, client, log, require_clean=True):
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=25)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if client:
            client.close()
    log.seek(0)
    content = log.read()
    log.close()
    if require_clean:
        assert process.returncode == 0, content
        assert 'Application shutdown complete' in content
        assert 'PBL4 HTTPS LAN dashboard:' in content


@pytest.fixture
def deployed(tmp_path):
    if not CADDY.is_file():
        pytest.skip('Approved project-local Caddy binary required for real proxy integration tests')
    https, backend = free_port(), free_port()
    path = config_file(tmp_path, HTTPS_PORT=str(https), BACKEND_PORT=str(backend),
                       ALLOWED_ORIGINS=f'https://127.0.0.1:{https}')
    config = LanConfig.load(path)
    process, client, log, context = launch(path, config, tmp_path)
    try:
        yield config, client, context, path
    finally:
        stop(process, client, log)


def login(client, origin, username='operator'):
    response = client.post('/api/auth/login', json={'username':username,'password': PASSWORD}, headers={'origin': origin})
    assert response.status_code == 200
    cookie = response.headers['set-cookie'].lower()
    assert 'secure' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie
    csrf = client.get('/api/auth/session').json()['csrf']
    return {'origin': origin, 'x-csrf-token': csrf}


def test_real_tls_wss_auth_csrf_assets_stop_and_disconnect(deployed):
    config, client, context, _ = deployed
    url = config.origin.replace('https:', 'wss:') + '/ws/telemetry'
    assert client.get('/api/auth/session').json()['authenticated'] is False
    assert client.get('/api/health').json()['hardware_enabled'] is False
    assert client.get('/navigation').status_code == client.get('/missions').status_code == 200
    assert client.get('/api/health', headers={'Host': 'evil.test'}).status_code != 200
    assert client.get('/api/health', headers={'Origin': 'https://evil.test'}).status_code == 403
    # Forged headers cannot change HTTPS/client-IP decisions at the proxy.
    assert client.get('/api/health', headers={'X-Forwarded-Proto': 'http', 'X-Forwarded-For': '8.8.8.8'}).status_code == 200
    direct = f'http://127.0.0.1:{config.backend_port}/api/health'
    assert httpx.get(direct, headers={'Host': f'{config.host}:{config.https_port}'}, trust_env=False).status_code == 403
    assert client.post('/api/missions', json={}).status_code == 401
    with pytest.raises(InvalidStatus):
        with connect(url,ssl=context,origin=config.origin,proxy=None):pass
    login(client,config.origin,'observer')
    for path in ('/docs', '/redoc', '/openapi.json', '/.env', '/src/main.tsx', '/@vite/client', '/assets/secret.map'):
        assert client.get(path).status_code == 404
    observer_cookie='; '.join(f'{c.name}={c.value}' for c in client.cookies.jar)
    with connect(url, ssl=context, origin=config.origin, additional_headers={'Cookie':observer_cookie}, proxy=None) as observer:
        observer.recv()
        observer.send(json.dumps({'type': 'stop'}))
        assert 'observer' in receive_until(observer, lambda f: f['type'] == 'error')['message']
    with pytest.raises(InvalidStatus):
        with connect(url, ssl=context, origin='https://evil.test', proxy=None):
            pass
    assert client.post('/api/auth/login', json={'username':'operator','password': 'incorrect'}, headers={'origin': config.origin}).status_code == 401
    headers = login(client, config.origin)
    assert client.post('/api/configuration', json={'type': 'configuration', 'action': 'reset_home'}, headers={'origin': config.origin}).status_code == 403
    assert client.post('/api/configuration', json={'type': 'configuration', 'action': 'reset_home'}, headers={**headers, 'x-csrf-token': 'invalid'}).status_code == 403
    cookie = '; '.join(f'{c.name}={c.value}' for c in client.cookies.jar)
    with connect(url, ssl=context, origin=config.origin, additional_headers={'Cookie': cookie}, proxy=None) as owner:
        owner.recv()
        owner.send(json.dumps({'type': 'control', 'linear': .1}))
        receive_until(owner, lambda f: f['type'] == 'telemetry' and f['mode'] == 'MANUAL')
        # Independent operator session, not the owner's cookie.
        with httpx.Client(base_url=config.origin, verify=context, trust_env=False) as other:
            login(other, config.origin)
            other_cookie = '; '.join(f'{c.name}={c.value}' for c in other.cookies.jar)
            with connect(url, ssl=context, origin=config.origin, additional_headers={'Cookie': other_cookie}, proxy=None) as stopper:
                stopper.recv()
                stopper.send(json.dumps({'type': 'stop'}))
                receive_until(stopper, lambda f: f['type'] == 'ack')
                assert client.get('/api/robot/status').json()['motors'][0]['actual_rpm'] == 0
        owner.send(json.dumps({'type': 'release'}))
        owner.send(json.dumps({'type': 'control', 'linear': .1}))
        receive_until(owner, lambda f: f['type'] == 'telemetry' and f['mode'] == 'MANUAL')
    for _ in range(40):
        status = client.get('/api/robot/status').json()
        if status['mode'] == 'STANDBY':
            break
        time.sleep(.05)
    assert status['mode'] == 'STANDBY' and status['motors'][0]['actual_rpm'] == 0
    with connect(url, ssl=context, origin=config.origin, additional_headers={'Cookie': cookie}, proxy=None) as reconnected:
        assert json.loads(reconnected.recv())['mode'] == 'STANDBY'
    with connect(config.origin.replace('https:', 'wss:') + '/ws/sensors', ssl=context, origin=config.origin, additional_headers={'Cookie':cookie}, proxy=None) as sensor:
        assert json.loads(sensor.recv())['camera']['status'] == 'NOT_CONNECTED'
    with connect(url, ssl=context, origin=config.origin, additional_headers={'Cookie': cookie}, proxy=None) as owner:
        owner.recv()
        owner.send(json.dumps({'type': 'control', 'linear': .1}))
        receive_until(owner, lambda f: f['type'] == 'telemetry' and f['mode'] == 'MANUAL')
        assert client.post('/api/auth/logout', headers=headers).status_code == 200
        with pytest.raises(ConnectionClosed):
            while True:
                owner.recv(timeout=3)
    assert client.get('/api/auth/session').json()['authenticated'] is False
    with pytest.raises(InvalidStatus):
        with connect(url, ssl=context, origin=config.origin, additional_headers={'Cookie': cookie}, proxy=None):pass


def test_https_restart_preserves_json_sqlite_and_revokes_sessions(tmp_path):
    if not CADDY.is_file():
        pytest.skip('Project-local Caddy required')
    https, backend = free_port(), free_port()
    path = config_file(tmp_path, HTTPS_PORT=str(https), BACKEND_PORT=str(backend), ALLOWED_ORIGINS=f'https://127.0.0.1:{https}')
    config = LanConfig.load(path)
    process, client, log, context = launch(path, config, tmp_path)
    try:
        headers = login(client, config.origin)
        cookie = client.cookies.get('pbl4_session')
        assert client.post('/api/configuration', headers=headers, json={'type': 'configuration', 'action': 'set_home', 'goal': {'x': 2, 'y': 2, 'yaw': .5}}).status_code == 200
        assert client.post('/api/waypoints', headers=headers, json={'type': 'waypoint', 'name': 'A', 'goal': {'x': 2, 'y': 1, 'yaw': .4}}).status_code == 200
        assert client.post('/api/missions', headers=headers, json={'name': 'Persist LAN', 'steps': [{'kind': 'wait', 'seconds': 1}]}).status_code == 200
        assert client.post('/api/missions?template=true', headers=headers, json={'name': 'LAN template', 'steps': [{'kind': 'home'}]}).status_code == 200
        duplicate = subprocess.run([str(ROOT / 'start-dashboard.sh'), '--no-build'], env={**os.environ, 'APP_MODE': 'local', 'DASHBOARD_PORT': str(free_port()), 'MISSION_DB_PATH': str(tmp_path / 'missions.sqlite3')}, capture_output=True, text=True, timeout=10)
        assert duplicate.returncode != 0 and 'production database lock' in duplicate.stderr
    finally:
        stop(process, client, log)


    with sqlite3.connect(tmp_path / 'missions.sqlite3') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    process, client, log, context = launch(path, config, tmp_path)
    try:
        assert client.get('/api/auth/session', headers={'Cookie': 'pbl4_session=' + cookie}).json()['authenticated'] is False
        login(client,config.origin)
        state = client.get('/api/robot/status').json()
        assert {key: state['pose'][key] for key in ('x', 'y', 'yaw')} == {'x': 2, 'y': 2, 'yaw': .5}
        assert state['navigation']['waypoints']['A']['yaw'] == .4
        saved = client.get('/api/missions').json()
        assert saved['queue'][0]['name'] == 'Persist LAN'
        assert saved['templates'][0]['name'] == 'LAN template'
    finally:
        stop(process, client, log)


def test_proxy_repeated_websocket_reconnects(deployed):
    config, client, context, _ = deployed
    url = config.origin.replace('https:', 'wss:') + '/ws/telemetry'
    login(client,config.origin,'observer')
    cookie='; '.join(f'{c.name}={c.value}' for c in client.cookies.jar)
    for _ in range(12):
        with connect(url, ssl=context, origin=config.origin, additional_headers={'Cookie':cookie}, proxy=None, open_timeout=3) as ws:
            assert json.loads(ws.recv(timeout=3))['simulation'] is True
        assert client.get('/api/health').status_code == 200


def test_forwarded_client_ip_cannot_evade_login_rate_limit(deployed):
    config, client, _, _ = deployed
    for attempt in range(6):
        response = client.post('/api/auth/login', json={'username':'operator','password': 'incorrect'},
                               headers={'Origin': config.origin, 'X-Forwarded-For': f'10.1.0.{attempt+1}'})
        assert response.status_code == (401 if attempt < 5 else 429)


def test_explicit_private_interface_https_and_loopback_backend(tmp_path):
    address = os.getenv('PBL4_LAN_TEST_IP')
    if not address:
        pytest.skip('Set PBL4_LAN_TEST_IP explicitly to a laptop RFC1918 interface for private-network staging')
    if not CADDY.is_file():
        pytest.skip('Approved project-local Caddy required')
    private_ipv4(address)
    password = secrets.token_urlsafe(32)
    https, backend = free_port(), free_port()
    path = config_file(tmp_path, LAN_HOST=address, LAN_BIND_IP=address, HTTPS_PORT=str(https),
                       BACKEND_PORT=str(backend), ALLOWED_HOSTS=address,
                       ALLOWED_ORIGINS=f'https://{address}:{https}', OPERATOR_PASSWORD_HASH=password_hash(password))
    config = LanConfig.load(path)
    process, client, log, context = launch(path, config, tmp_path)
    try:
        for host, target in ((address, backend), ('127.0.0.1', https)):
            with socket.socket() as probe:
                probe.settimeout(1)
                assert probe.connect_ex((host, target)) != 0
        assert client.get('/api/health').json()['hardware_enabled'] is False
        assert client.get('/api/auth/session').json()['authenticated'] is False
        AccountStore(tmp_path/'accounts.json').update('operator',password_hash=password_hash(password))
        assert client.post('/api/auth/login', headers={'Origin': config.origin}, json={'username':'operator','password': password}).status_code == 200
        cookie = '; '.join(f'{c.name}={c.value}' for c in client.cookies.jar)
        with connect(config.origin.replace('https:', 'wss:') + '/ws/telemetry', ssl=context,
                     origin=config.origin, additional_headers={'Cookie': cookie}, proxy=None) as ws:
            ws.recv()
            ws.send(json.dumps({'type': 'control', 'linear': .1}))
            receive_until(ws, lambda f: f['type'] == 'telemetry' and f['mode'] == 'MANUAL')
            ws.send(json.dumps({'type': 'stop'}))
            receive_until(ws, lambda f: f['type'] == 'ack')
            assert client.get('/api/robot/status').json()['motors'][0]['actual_rpm'] == 0
    finally:
        stop(process, client, log)
