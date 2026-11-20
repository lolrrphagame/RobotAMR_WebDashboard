import math
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.main import app
from app.operations import DefinitionStore,MissionDefinition,OperationsCommand
from app.models import ControlCommand,Goal
from app.simulator import RobotSimulator,AUTONOMOUS_TIMEOUT


def definition(name='Delivery',steps=None):return MissionDefinition(name=name,steps=steps or [{'kind':'wait','seconds':.3}])
def op(r,action,owner='owner'):return r.command(OperationsCommand(type='operations',action=action),owner)
def advance(r,n=1):
    for _ in range(n):
        r.command(ControlCommand(type='heartbeat'),'owner');r.tick(.1)


def test_definitions_validation_capacity_queue_templates():
    r=RobotSimulator()
    for body in [{'name':' ','steps':[{'kind':'home'}]},{'name':'x','steps':[]},{'name':'x','steps':[{'kind':'wait','seconds':0}]}]:
        with pytest.raises(ValidationError):MissionDefinition.model_validate(body)
    with pytest.raises(ValueError):r.operations.create(definition(steps=[{'kind':'waypoint','waypoint':'A'}]))
    for i in range(20):r.operations.create(definition(str(i)))
    with pytest.raises(ValueError,match='capacity'):r.operations.create(definition())
    ids=[d['id'] for d in r.operations.queue];r.operations.reorder(ids[::-1]);assert r.operations.queue[0]['id']==ids[-1]
    with pytest.raises(ValueError):r.operations.reorder([ids[0]]*20)
    r.operations.create(definition(),True);assert r.operations.current is None
    r.operations.remove(ids[0]);assert len(r.operations.queue)==19


def test_wait_pause_resume_stop_and_no_automatic_next():
    r=RobotSimulator();r.operations.create(definition());r.operations.create(definition('Next'))
    op(r,'start_next');advance(r);op(r,'pause');remaining=r.operations.current['wait_remaining'];advance(r,10)
    assert r.operations.current['wait_remaining']==remaining and r.rpm==[0,0]
    assert not r.command(ControlCommand(type='control',linear=.1),'owner')
    op(r,'resume');advance(r,4)
    assert r.operations.current is None and len(r.operations.queue)==1
    assert r.operations.history()[0]['status']=='completed'
    advance(r,10);assert r.operations.current is None
    op(r,'start_next');advance(r);r.command(ControlCommand(type='stop'),'other');advance(r,10)
    assert r.operations.current is None and r.rpm==[0,0]
    assert r.operations.history()[0]['status']=='cancelled'
    assert r.operations.analytics()['total']==2 and r.operations.analytics()['success_rate']==50


def test_abc_home_sequence_distance_and_history():
    r=RobotSimulator()
    for name,x,y in [('A',2,1),('B',2,2),('C',1,2)]:r.mission.save(name,Goal(x=x,y=y,name=name))
    r.operations.create(definition(steps=[{'kind':'waypoint','waypoint':n} for n in 'ABC']+[{'kind':'wait','seconds':.2},{'kind':'home'}]))
    op(r,'start_next')
    for _ in range(3000):
        advance(r)
        if not r.operations.active:break
    record=r.operations.history()[0]
    assert record['status']=='completed' and record['completed_steps']==5
    assert record['distance']>3 and record['duration']>1
    assert record['waypoint_visits']==3 and math.dist(r.state.pose[:2],(1,1))<.035
    assert all(s['status']=='completed' for s in record['steps'])
    assert record['start_pose']==[1,1,0] and record['end_pose']==list(r.state.pose)


def test_disconnect_heartbeat_and_simultaneous_clients(monkeypatch):
    r=RobotSimulator();r.operations.create(definition(steps=[{'kind':'wait','seconds':10}]))
    op(r,'start_next');advance(r);r.disconnect('observer');assert r.operations.current['status']=='running'
    with pytest.raises(ValueError):op(r,'pause','other')
    r.disconnect('owner');assert r.operations.current['status']=='paused' and r.owner is None
    advance(r,10);assert r.operations.current['status']=='paused'
    op(r,'resume');monkeypatch.setattr('app.simulator.time.monotonic',lambda:r.last_lease+AUTONOMOUS_TIMEOUT+.01)
    r.tick(.1);assert r.operations.current['status']=='paused' and r.rpm==[0,0]


def test_collision_and_unreachable_path_record_failure():
    r=RobotSimulator();r.operations.create(definition(steps=[{'kind':'pose','pose':{'x':2,'y':1}}]))
    op(r,'start_next');advance(r)
    cx,cy=r.grid.cell(r.state.pose);r.grid.data[cy*r.grid.width+cx]=100;advance(r)
    assert r.operations.history()[0]['status']=='failed' and r.rpm==[0,0]
    r=RobotSimulator();r.operations.create(definition(steps=[{'kind':'pose','pose':{'x':4.5,'y':1}}]))
    for y in range(r.grid.height):r.grid.data[y*r.grid.width+16]=100
    op(r,'start_next');advance(r)
    assert r.operations.history()[0]['status']=='failed'
    assert 'path' in r.operations.history()[0]['reason'].lower()


def test_sqlite_restart_recovers_pending_and_interrupts_active(tmp_path):
    path=str(tmp_path/'missions.db');store=DefinitionStore(path);r=RobotSimulator(operations_store=store)
    r.operations.create(definition('Long', [{'kind':'wait','seconds':100}]))
    r.operations.create(definition('Pending'));r.operations.create(definition('Template'),True)
    op(r,'start_next');advance(r,12);store.close()
    restored=RobotSimulator(operations_store=DefinitionStore(path))
    assert restored.operations.current is None and restored.owner is None and restored.rpm==[0,0]
    assert len(restored.operations.queue)==1 and len(restored.operations.templates)==1
    assert restored.operations.history()[0]['status']=='interrupted'
    assert restored.operations.analytics()['interrupted']==1
    advance(restored,10);assert restored.operations.current is None


def test_operations_api_history_filters_and_csv():
    with TestClient(app) as client:
        assert client.post('/api/missions',json={'name':'Wait job','steps':[{'kind':'wait','seconds':.1}]}).status_code==200
        assert client.delete('/api/missions/queue').status_code==400
        with client.websocket_connect('/ws/telemetry') as ws:
            ws.receive_json();ws.send_json({'type':'operations','action':'start_next'})
            for _ in range(30):
                frame=ws.receive_json()
                if frame['type']=='telemetry' and frame['operations']['active'] is None:break
        records=client.get('/api/missions/history?status=completed&q=WAIT').json()['records']
        assert len(records)==1
        assert 'Wait job' in client.get('/api/missions/history?format=csv').text
        assert client.get('/api/missions').json()['analytics']['completed']==1


def test_stop_during_navigation_cannot_restart_next_step_or_next_job():
    r=RobotSimulator()
    r.operations.create(definition(steps=[{'kind':'pose','pose':{'x':2,'y':1}},{'kind':'home'}]))
    r.operations.create(definition('Pending'))
    op(r,'start_next');advance(r,25)
    assert any(abs(v)>0 for v in r.rpm)
    r.command(ControlCommand(type='stop'),'observer')
    pose=r.state.pose
    advance(r,30)
    assert r.state.pose==pose and r.rpm==r.targets()==[0,0]
    assert r.operations.current is None and len(r.operations.queue)==1
    assert r.operations.history()[0]['status']=='cancelled'
