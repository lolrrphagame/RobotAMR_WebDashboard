"""Account provisioning, endpoint authorization, live revocation and migration."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.accounts import AccountStore, make_password_hash, verify_password, main
from app.main import app
from app.security import password_hash


@pytest.fixture
def secured(monkeypatch, tmp_path):
    store = AccountStore(tmp_path / 'accounts.json')
    for name, role in (('alice', 'operator'), ('bob', 'operator'), ('viewer', 'observer')):
        store.create(name, role, password_hash('isolated-password'))
    monkeypatch.setenv('APP_MODE', 'lan')
    monkeypatch.setenv('ACCOUNT_STORE_PATH', str(store.path))
    monkeypatch.setenv('ALLOWED_HOSTS', 'robot.test')
    monkeypatch.setenv('ALLOWED_ORIGINS', 'https://robot.test')
    with TestClient(app, base_url='https://robot.test') as client:
        yield client, store


def sign_in(client, name):
    assert client.post('/api/auth/login', json={'username': name, 'password': 'isolated-password'},
                       headers={'Origin': 'https://robot.test'}).status_code == 200
    return {'Origin': 'https://robot.test', 'X-CSRF-Token': client.get('/api/auth/session').json()['csrf']}


def test_every_sensitive_http_route_denies_anonymous(secured):
    client, _ = secured
    for route in app.routes:
        if route.path.startswith('/api/') and route.path not in ('/api/health', '/api/auth/login', '/api/auth/session'):
            for method in getattr(route, 'methods', []):
                response = client.request(method, route.path.replace('{id}', 'missing'))
                assert response.status_code == 401, (method, route.path, response.text)
    for path in ('/api/waypoints', '/api/diagnostics/future', '/api/future-sensitive-endpoint'):
        assert client.get(path).status_code == 401
    assert client.get('/api/health').json() == {'status': 'ok', 'simulation': True, 'hardware_enabled': False}
    state = client.get('/api/auth/session').json()
    assert state['role'] is None and state['username'] is None and not state['authenticated']


@pytest.mark.parametrize('path', ['/ws/telemetry', '/ws/sensors'])
def test_anonymous_websockets_rejected_before_first_frame(secured, path):
    client, _ = secured
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('wss://robot.test' + path, headers={'Origin': 'https://robot.test'}):
            pytest.fail('Anonymous socket was accepted')


def test_observer_can_monitor_and_logout_but_cannot_mutate_any_route(secured):
    client, _ = secured
    headers = sign_in(client, 'viewer')
    session = client.get('/api/auth/session').json()
    assert session['role'] == 'observer' and session['username'] == 'viewer' and session['authenticated']
    for path in ('/api/robot/status', '/api/map', '/api/configuration', '/api/events', '/api/diagnostics/history',
                 '/api/sensors', '/api/sensors/lidar', '/api/sensors/camera', '/api/missions', '/api/missions/history'):
        assert client.get(path).status_code == 200, path
    for route in app.routes:
        if route.path.startswith('/api/') and route.path not in ('/api/auth/login', '/api/auth/logout'):
            for method in getattr(route, 'methods', []):
                if method not in ('GET', 'HEAD', 'OPTIONS'):
                    assert client.request(method, route.path.replace('{id}', 'missing'), headers=headers).status_code == 403
    with client.websocket_connect('wss://robot.test/ws/sensors', headers={'Origin': 'https://robot.test'}) as ws:
        assert ws.receive_json()['simulation'] is True
    assert client.post('/api/auth/logout').status_code == 403
    assert client.post('/api/auth/logout', headers=headers).status_code == 200
    assert client.get('/api/map').status_code == 401


def test_client_role_claim_and_invalid_cookie_never_grant_access(secured):
    client, _ = secured
    assert client.get('/api/map',headers={'Cookie':'pbl4_session=forged'}).status_code==401
    response=client.post('/api/auth/login',json={'username':'viewer','password':'isolated-password','role':'operator'},headers={'Origin':'https://robot.test'})
    assert response.status_code==200
    assert client.get('/api/auth/session').json()['role']=='observer'
    assert client.post('/api/configuration',json={},headers={'Origin':'https://robot.test'}).status_code==403


@pytest.mark.parametrize('name', ['alice', 'viewer'])
@pytest.mark.parametrize('path', ['/ws/telemetry','/ws/sensors'])
def test_expiration_closes_both_roles_and_both_streams(secured,name,path):
    client,_=secured
    sign_in(client,name)
    with client.websocket_connect('wss://robot.test'+path,headers={'Origin':'https://robot.test'}) as ws:
        ws.receive_json()
        for session in app.state.security.sessions.values():session['expires']=0
        with pytest.raises(WebSocketDisconnect):
            while True:ws.receive_json()
    assert client.get('/api/events').status_code==401


@pytest.mark.parametrize('command', [
    {'type': 'stop'}, {'type': 'release'}, {'type': 'heartbeat'}, {'type': 'control', 'linear': .1},
    {'type': 'navigation', 'action': 'home'}, {'type': 'operations', 'action': 'start_next'},
    {'type': 'configuration', 'action': 'reset_home'},
])
def test_observer_socket_rejects_every_control_category(secured, command):
    client, _ = secured
    sign_in(client, 'viewer')
    with client.websocket_connect('wss://robot.test/ws/telemetry', headers={'Origin': 'https://robot.test'}) as ws:
        ws.receive_json()
        ws.send_json(command)
        for _ in range(20):
            frame = ws.receive_json()
            if frame['type'] == 'error':break
        assert frame['type'] == 'error'
        assert app.state.robot.owner is None and app.state.robot.rpm == [0, 0]


@pytest.mark.parametrize('change', ['disable', 'revoke', 'role', 'password', 'corrupt'])
@pytest.mark.parametrize('path', ['/ws/telemetry', '/ws/sensors'])
def test_account_changes_revoke_open_streams_without_restart(secured, change, path):
    client, store = secured
    sign_in(client, 'alice')
    with client.websocket_connect('wss://robot.test' + path, headers={'Origin': 'https://robot.test'}) as ws:
        ws.receive_json()
        if change == 'disable':store.update('alice', enabled=False)
        elif change == 'role':store.update('alice', role='observer')
        elif change == 'password':store.update('alice', password_hash=password_hash('new-isolated-password'))
        elif change == 'corrupt':store.path.write_text('{invalid')
        else:store.update('alice')
        with pytest.raises(WebSocketDisconnect):
            while True:ws.receive_json()
    assert client.get('/api/robot/status').status_code == 401
    assert not client.get('/api/auth/session').json()['authenticated']


def test_disabling_motion_owner_halts_and_second_operator_can_stop(secured):
    client, store = secured
    sign_in(client, 'alice')
    with client.websocket_connect('wss://robot.test/ws/telemetry', headers={'Origin': 'https://robot.test'}) as owner:
        owner.receive_json(); owner.send_json({'type': 'control', 'linear': .1})
        for _ in range(20):
            frame=owner.receive_json()
            if frame['type']=='telemetry' and frame['mode']=='MANUAL':break
        assert app.state.robot.owner is not None
        client.cookies.clear()  # Independent browser session; do not replace/revoke Alice's login.
        sign_in(client, 'bob')
        with client.websocket_connect('wss://robot.test/ws/telemetry', headers={'Origin': 'https://robot.test'}) as other:
            other.receive_json();other.send_json({'type':'stop'})
            for _ in range(20):
                if other.receive_json()['type']=='ack':break
            assert app.state.robot.rpm==[0,0]
        # A fresh controller can be revoked while it owns motion.
    sign_in(client, 'alice')
    with client.websocket_connect('wss://robot.test/ws/telemetry', headers={'Origin':'https://robot.test'}) as owner:
        owner.receive_json();owner.send_json({'type':'control','linear':.1})
        for _ in range(20):
            frame=owner.receive_json()
            if frame['type']=='telemetry' and frame['mode']=='MANUAL':break
        store.update('alice',enabled=False)
        with pytest.raises(WebSocketDisconnect):
            while True:owner.receive_json()
    assert app.state.robot.rpm==[0,0] and app.state.robot.owner is None


def test_new_hashes_and_atomic_failure_preserve_accounts(tmp_path, monkeypatch):
    encoded = make_password_hash('strong-isolated-password')
    assert encoded.startswith('scrypt$32768$8$3$')
    assert verify_password('strong-isolated-password', encoded)
    assert not verify_password('incorrect', encoded)
    store=AccountStore(tmp_path/'accounts.json');store.create('Alice','operator',encoded)
    original=store.path.read_bytes()
    def fail(*args):raise OSError('injected atomic save failure')
    monkeypatch.setattr('app.accounts.os.replace', fail)
    with pytest.raises(OSError):store.update('alice',enabled=False)
    assert store.path.read_bytes()==original and store.load()['alice']['enabled']
    assert store.path.stat().st_mode & 0o077 == 0


def test_cli_migrates_hash_without_deleting_config_and_hides_secrets(tmp_path, monkeypatch, capsys):
    path=tmp_path/'accounts.json';config=tmp_path/'lan.env'
    encoded=password_hash('existing-private-password')
    config.write_text('OPERATOR_PASSWORD_HASH='+encoded+'\n');config.chmod(0o600)
    original=config.read_bytes()
    def run(*args):
        monkeypatch.setattr('sys.argv',['accounts','--store',str(path),*args]);main()
    run('migrate-legacy','operator','--config',str(config))
    assert config.read_bytes()==original and AccountStore(path).load()['operator']['password_hash']==encoded
    run('list'); output=capsys.readouterr().out
    assert 'operator' in output and encoded not in output and 'existing-private-password' not in output
    monkeypatch.setattr('app.accounts.getpass.getpass', lambda prompt:'new-observer-password')
    run('create','viewer','--role','observer')
    before=AccountStore(path).load()['viewer']['revision']
    run('revoke','viewer');assert AccountStore(path).load()['viewer']['revision']!=before
    run('disable','viewer');assert not AccountStore(path).load()['viewer']['enabled']
    run('enable','viewer');run('set-role','viewer','operator');run('reset-password','viewer')
    assert AccountStore(path).load()['viewer']['role']=='operator'
    with pytest.raises(SystemExit):run('migrate-legacy','operator','--config',str(config))
    assert config.read_bytes()==original
