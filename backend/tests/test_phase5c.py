"""Acceptance regressions use only isolated simulator/configuration/database state."""
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models import ControlCommand, ConfigurationCommand, Goal, WaypointCommand
from app.configuration import ConfigurationStore
from app.operations import DefinitionStore, MissionDefinition, OperationsCommand
from app.simulator import RobotSimulator
from app.backup import backup


def test_shared_encoded_frame_invalidates_on_tick_and_stop(monkeypatch):
    robot=RobotSimulator()
    original=json.dumps;calls=[]
    def encode(*args,**kwargs):calls.append(1);return original(*args,**kwargs)
    monkeypatch.setattr('app.simulator.json.dumps',encode)
    first=robot.broadcast_text()
    assert all(robot.broadcast_text() is first for _ in range(8)) and len(calls)==1
    robot.tick(.1);second=robot.broadcast_text()
    assert second!=first
    robot.command(ControlCommand(type='control',linear=.1),'operator');robot.tick(.1)
    robot.command(ControlCommand(type='stop'),'second-operator')
    stopped=json.loads(robot.broadcast_text())
    assert stopped['mode']=='STANDBY' and all(m['actual_rpm']==0 for m in stopped['motors'])
    assert stopped['session_id']==robot.session_id and stopped['pose']['x']==robot.state.pose[0]
    robot.operations.store.close()


def record(index,status='completed'):
    return {'id':str(index),'name':'Straße_%' if index%2==0 else 'Archive', 'status':status,
        'duration':float(index),'distance':index/10,'waypoint_visits':index%3,
        'started_at':'2026-11-22T00:00:00+00:00','finished_at':'2026-11-22T00:00:01+00:00',
        'steps':[],'mission_id':'saved','completed_steps':1,'reason':'test','start_pose':[1,1,0],'end_pose':[1,1,0]}


def test_bounded_history_total_unicode_filter_and_sql_analytics():
    with TestClient(app) as client:
        store=app.state.robot.operations.store
        def seed():
            for index in range(1005):store.save_run(record(index))
            store.save_run(record(2000,'running'));store.save_run(record(2001,'paused'))
        client.portal.call(seed)  # SQLite remains owned by the app event-loop thread.
        def forbidden(*args,**kwargs):raise AssertionError('Read APIs must not decode the complete archive')
        store.records=forbidden
        history=client.get('/api/missions/history').json()
        assert len(history['records'])==1000 and history['total']==1005
        summary=client.get('/api/missions').json()
        assert len(summary['history'])==200 and summary['analytics']['total']==1005
        filtered=client.get('/api/missions/history',params={'q':'STRASSE_%'}).json()
        assert filtered['total']==503 and all(r['name']=='Straße_%' for r in filtered['records'])
        assert client.get('/api/missions/history',params={'q':"' OR 1=1 --"}).json()['total']==0
        assert client.get('/api/missions/history?format=csv').text.count('\n')==1006
        assert summary['analytics']['average_duration']==502
        assert summary['analytics']['trends']==[{'date':'2026-11-22','missions':1005}]


def test_sql_analytics_preserves_terminal_status_semantics():
    store=DefinitionStore()
    statuses=['completed','cancelled','failed','interrupted','paused','running']
    for index,status in enumerate(statuses):store.save_run(record(index,status))
    result=store.analytics()
    assert result['total']==4 and result['success_rate']==25
    assert result['average_duration']==1.5 and result['waypoint_visits']==3
    assert result['distance']==pytest.approx(.6)
    assert all(result[status]==1 for status in statuses[:4])
    store.close()


def test_missing_sqlite_json_support_fails_before_data_changes(monkeypatch):
    class Unsupported:
        closed=False
        def execute(self,query):
            assert query=="SELECT json_valid('{}')"
            raise sqlite3.OperationalError('no such function: json_valid')
        def close(self):self.closed=True
    connection=Unsupported()
    monkeypatch.setattr('app.operations.sqlite3.connect',lambda *args,**kwargs:connection)
    with pytest.raises(ValueError,match='SQLite JSON functions'):DefinitionStore()
    assert connection.closed


def test_online_wal_backup_restore_keeps_home_waypoint_history_and_stops(tmp_path):
    config=tmp_path/'robot-config.json';database=tmp_path/'missions.sqlite3'
    robot=RobotSimulator(store=ConfigurationStore(config),operations_store=DefinitionStore(database))
    robot.command(ConfigurationCommand(type='configuration',action='set_home',goal=Goal(x=2,y=2,yaw=.3)),'operator')
    robot.command(WaypointCommand(type='waypoint',name='A',goal=Goal(x=2,y=1,yaw=.4)),'operator')
    robot.operations.create(MissionDefinition(name='Recovery test',steps=[{'kind':'wait','seconds':30}]))
    robot.command(OperationsCommand(type='operations',action='start_next'),'operator');robot.tick(.1)
    assert database.with_name(database.name+'-wal').stat().st_size>0
    backup(tmp_path/'backup',database,config)
    assert (tmp_path/'backup').stat().st_mode & 0o077 == 0
    assert all((tmp_path/'backup'/name).stat().st_mode & 0o077 == 0 for name in ('missions.sqlite3','robot-config.json','manifest.json'))
    # Restore only into a fresh isolated directory, never over source or production data.
    shutil.copytree(tmp_path/'backup',tmp_path/'restored')
    restored=RobotSimulator(store=ConfigurationStore(tmp_path/'restored/robot-config.json'),operations_store=DefinitionStore(tmp_path/'restored/missions.sqlite3'))
    assert restored.state.pose==pytest.approx((2,2,.3)) and restored.rpm==[0,0] and restored.owner is None
    assert restored.mission.waypoints['A'].yaw==.4
    assert restored.operations.current is None and restored.operations.history()[0]['status']=='interrupted'
    assert robot.operations.current['status']=='running'  # Restore did not change the source.
    with sqlite3.connect(tmp_path/'restored/missions.sqlite3') as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    restored.operations.store.close();robot.operations.store.close()


def test_backup_closes_both_sqlite_connections(tmp_path,monkeypatch):
    import app.backup as backup_module
    source=tmp_path/'source.sqlite3';connection=sqlite3.connect(source)
    connection.execute('CREATE TABLE evidence(value)');connection.commit();connection.close()
    original=sqlite3.connect;closed=[]
    class Tracked:
        def __init__(self,*args,**kwargs):self.connection=original(*args,**kwargs)
        def backup(self,target):return self.connection.backup(target.connection)
        def close(self):closed.append(self);self.connection.close()
    monkeypatch.setattr(backup_module.sqlite3,'connect',Tracked)
    backup_module.backup(tmp_path/'backup',source,tmp_path/'missing.json')
    assert len(closed)==2


@pytest.mark.parametrize('arguments',[['--seconds','0'],['--seconds','3601'],['--observers','7']])
def test_soak_rejects_unbounded_load_before_startup(tmp_path,arguments):
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run([str(root/'backend/.venv/bin/python'),str(root/'backend/tools/phase5c.py'),
                           '--output',str(tmp_path/'report.json'),*arguments],capture_output=True,text=True,timeout=5)
    assert result.returncode!=0 and 'Bound duration' in result.stderr
    assert not (tmp_path/'report.json').exists()
