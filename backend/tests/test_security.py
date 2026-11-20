import sqlite3
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.security import password_hash,Security
from app.simulator import RobotSimulator
from app.models import ControlCommand
from app.operations import MissionDefinition,OperationsCommand

@pytest.fixture
def lan(monkeypatch):
    monkeypatch.setenv('APP_MODE','lan');monkeypatch.setenv('ALLOWED_HOSTS','robot.test')
    monkeypatch.setenv('ALLOWED_ORIGINS','https://robot.test');monkeypatch.setenv('OPERATOR_PASSWORD_HASH',password_hash('test-password'))
    with TestClient(app,base_url='https://robot.test') as c:yield c


def test_lan_sessions_observers_csrf_logout_and_hosts(lan):
    c=lan;origin={'origin':'https://robot.test'}
    assert c.get('/api/auth/session').json()['role']=='observer'
    assert c.post('/api/configuration',json={'type':'configuration','action':'reset_home'},headers=origin).status_code==401
    assert c.post('/api/auth/login',json={'password':'bad'},headers=origin).status_code==401
    assert c.post('/api/auth/login',json={'password':'test-password'},headers=origin).status_code==200
    state=c.get('/api/auth/session').json();assert state['role']=='operator'
    assert c.post('/api/configuration',json={'type':'configuration','action':'reset_home'},headers=origin).status_code==403
    headers={**origin,'x-csrf-token':state['csrf']}
    assert c.post('/api/configuration',json={'type':'configuration','action':'reset_home'},headers=headers).status_code==200
    assert c.get('/api/health',headers={'host':'evil.test'}).status_code==400
    assert c.post('/api/auth/logout',headers=headers).status_code==200
    assert c.get('/api/auth/session').json()['role']=='observer'


def test_observer_websocket_cannot_command(lan):
    with lan.websocket_connect('wss://robot.test/ws/telemetry',headers={'origin':'https://robot.test'}) as ws:
        ws.receive_json();ws.send_json({'type':'control','linear':.1})
        for _ in range(10):
            m=ws.receive_json()
            if m['type']=='error':break
        assert 'observer' in m['message']
        assert app.state.robot.owner is None


def test_session_revocation_disconnects_motion(lan):
    c=lan;headers={'origin':'https://robot.test'}
    c.post('/api/auth/login',json={'password':'test-password'},headers=headers)
    with c.websocket_connect('wss://robot.test/ws/telemetry',headers=headers) as ws:
        ws.receive_json();ws.send_json({'type':'control','linear':.1})
        for _ in range(10):
            frame=ws.receive_json()
            if frame['type']=='telemetry' and frame['mode']=='MANUAL':break
        c.post('/api/auth/logout',headers={**headers,'x-csrf-token':c.get('/api/auth/session').json()['csrf']})
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect):
            while True:ws.receive_json()
    assert app.state.robot.rpm==[0,0]


def test_loopback_does_not_silently_authorize_remote_clients_and_limits():
    with TestClient(app,client=('192.168.1.20',4567)) as c:
        assert c.get('/api/health').status_code==403
    with TestClient(app) as c:
        assert c.post('/api/missions',content=' '*32769).status_code==413
        assert c.get('/api/health',headers={'origin':'https://evil.test'}).status_code==403


def test_stop_replay_inhibition_and_explicit_release():
    r=RobotSimulator();r.command(ControlCommand(type='control',linear=.1),'a');r.tick(.1)
    r.command(ControlCommand(type='stop'),'b');pose=r.state.pose
    assert not r.command(ControlCommand(type='control',linear=.1),'a')
    r.tick(.1);assert r.state.pose==pose and r.rpm==[0,0]
    r.command(ControlCommand(type='release'),'a')
    assert r.command(ControlCommand(type='control',linear=.1),'a')


def test_stop_survives_sqlite_failure(monkeypatch):
    r=RobotSimulator();r.operations.create(MissionDefinition(name='Test',steps=[{'kind':'wait','seconds':10}]))
    r.command(OperationsCommand(type='operations',action='start_next'),'a')
    def fail(*args):raise sqlite3.OperationalError('injected disk error')
    monkeypatch.setattr(r.operations.store,'save_run',fail)
    r.stop();assert r.rpm==r.targets()==[0,0] and r.owner is None and r.operations.current is None
    assert r.operations.persistence_fault


def test_lan_fails_closed_without_explicit_credentials(monkeypatch):
    monkeypatch.setenv('APP_MODE','lan');monkeypatch.delenv('OPERATOR_PASSWORD_HASH',raising=False)
    with pytest.raises(ValueError):Security()


def test_authenticated_stop_from_second_socket_and_cookie_flags(lan):
    c=lan;headers={'origin':'https://robot.test'}
    response=c.post('/api/auth/login',json={'password':'test-password'},headers=headers)
    cookie=response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'secure' in cookie and 'samesite=strict' in cookie
    with c.websocket_connect('wss://robot.test/ws/telemetry',headers=headers) as a:
        a.receive_json();a.send_json({'type':'control','linear':.1})
        for _ in range(10):
            frame=a.receive_json()
            if frame['type']=='telemetry' and frame['mode']=='MANUAL':break
        with c.websocket_connect('wss://robot.test/ws/telemetry',headers=headers) as b:
            b.receive_json();b.send_json({'type':'stop'})
            for _ in range(10):
                if b.receive_json()['type']=='ack':break
            assert app.state.robot.rpm==[0,0]
            a.send_json({'type':'control','linear':.1})
            for _ in range(10):
                if a.receive_json()['type']=='error':break
            assert app.state.robot.owner is None


def test_login_rate_limit_and_http_tls_requirement(lan):
    for _ in range(5):assert lan.post('/api/auth/login',json={'password':'wrong'},headers={'origin':'https://robot.test'}).status_code==401
    assert lan.post('/api/auth/login',json={'password':'test-password'},headers={'origin':'https://robot.test'}).status_code==429
    assert lan.get('http://robot.test/api/health').status_code==403


def test_backup_and_legacy_schema_preserve_data(tmp_path):
    import json
    from app.operations import DefinitionStore
    from app.backup import backup
    path=tmp_path/'missions.sqlite3';store=DefinitionStore(str(path))
    store.replace('queue',[{'id':'saved','name':'Preserve me','definition':{'name':'Preserve me','steps':[{'kind':'home'}]}}])
    store.db.execute('PRAGMA user_version=0');store.close()
    store=DefinitionStore(str(path));assert store.db.execute('PRAGMA user_version').fetchone()[0]==1
    config=tmp_path/'robot-config.json';config.write_text(json.dumps({'version':1,'home':{'x':2,'y':2,'yaw':0},'waypoints':{}}))
    backup(tmp_path/'backup',path,config)
    with sqlite3.connect(tmp_path/'backup'/'missions.sqlite3') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT id FROM definitions').fetchone()[0]=='saved'
    assert (tmp_path/'backup'/'robot-config.json').read_bytes()==config.read_bytes()
    with pytest.raises(ValueError):backup(tmp_path/'backup',path,config)
    store.close()
