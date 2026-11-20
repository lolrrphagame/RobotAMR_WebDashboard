"""Real production entrypoint/restart smoke test, with temporary persisted data."""
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import time
import httpx
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[2]


def available_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        return s.getsockname()[1]


def launch(tmp_path,port):
    env={**os.environ,'APP_MODE':'local','DASHBOARD_PORT':str(port),
         'MISSION_DB_PATH':str(tmp_path/'missions.sqlite3'),'ROBOT_CONFIG_PATH':str(tmp_path/'robot-config.json')}
    log=(tmp_path/f'server-{time.monotonic_ns()}.log').open('w+')
    process=subprocess.Popen([str(ROOT/'start-dashboard.sh'),'--no-build'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    client=httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=2)
    for _ in range(100):
        if process.poll() is not None:break
        try:
            if client.get('/api/health').status_code==200:return process,client,log
        except httpx.HTTPError:pass
        time.sleep(.05)
    process.terminate();process.wait(timeout=15);log.seek(0)
    raise AssertionError('Production startup failed: '+log.read())


def stop(process,client,log):
    if process.poll() is None:process.send_signal(signal.SIGTERM)
    try:process.wait(timeout=15)
    finally:
        if process.poll() is None:process.kill();process.wait()
        client.close()
    log.seek(0);text=log.read();log.close()
    assert 'Application shutdown complete' in text
    assert '127.0.0.1' in text


def test_real_launcher_wss_stop_and_saved_data_survive_restart(tmp_path):
    port=available_port();process,c,log=launch(tmp_path,port)
    try:
        duplicate=subprocess.run([str(ROOT/'start-dashboard.sh'),'--no-build'],env={**os.environ,'APP_MODE':'local','DASHBOARD_PORT':str(available_port()),'MISSION_DB_PATH':str(tmp_path/'missions.sqlite3')},text=True,capture_output=True,timeout=10)
        assert duplicate.returncode!=0 and 'production database lock' in duplicate.stdout+duplicate.stderr
        assert c.get('/').status_code==200
        assert c.get('/navigation').status_code==200 and c.get('/missions').status_code==200
        assert c.get('/docs').status_code==404
        assert c.get('/api/health',headers={'host':'192.168.1.2'}).status_code==400
        assert c.post('/api/configuration',json={'type':'configuration','action':'set_home','goal':{'x':2,'y':2,'yaw':.5}}).status_code==200
        assert c.post('/api/waypoints',json={'type':'waypoint','name':'A','goal':{'x':2,'y':1,'yaw':.4}}).status_code==200
        with connect(f'ws://127.0.0.1:{port}/ws/telemetry',origin=f'http://127.0.0.1:{port}',open_timeout=3) as ws:
            assert json.loads(ws.recv())['simulation'] is True
            ws.send(json.dumps({'type':'control','linear':.1}))
            for _ in range(30):
                f=json.loads(ws.recv())
                if f['type']=='telemetry' and f['mode']=='MANUAL':break
            assert f['mode']=='MANUAL'
            with connect(f'ws://127.0.0.1:{port}/ws/telemetry',origin=f'http://127.0.0.1:{port}') as other:
                other.recv();other.send(json.dumps({'type':'stop'}))
                for _ in range(30):
                    if json.loads(other.recv())['type']=='ack':break
                assert c.get('/api/robot/status').json()['motors'][0]['actual_rpm']==0
            c.post('/api/missions',json={'name':'Saved completion','steps':[{'kind':'wait','seconds':.1}]})
            ws.send(json.dumps({'type':'operations','action':'start_next'}))
            for _ in range(30):
                f=json.loads(ws.recv())
                if f['type']=='telemetry' and f['operations']['active'] is None and c.get('/api/missions').json()['analytics']['completed']==1:break
            assert c.get('/api/missions').json()['analytics']['completed']==1
            for name in ('Interrupted run','Pending job'):
                assert c.post('/api/missions',json={'name':name,'steps':[{'kind':'wait','seconds':60}]}).status_code==200
            assert c.post('/api/missions?template=true',json={'name':'Template','steps':[{'kind':'home'}]}).status_code==200
            ws.send(json.dumps({'type':'operations','action':'start_next'}))
            for _ in range(30):
                f=json.loads(ws.recv())
                if f['type']=='telemetry' and f['operations']['active'] is not None:break
            assert c.get('/api/missions').json()['active']['name']=='Interrupted run'
    finally:stop(process,c,log)
    with sqlite3.connect(tmp_path/'missions.sqlite3') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    process,c,log=launch(tmp_path,port)
    try:
        status=c.get('/api/robot/status').json()
        assert status['pose']['x']==2 and status['pose']['y']==2 and status['pose']['yaw']==.5
        assert status['mode']=='STANDBY' and status['motors'][0]['actual_rpm']==0
        assert status['navigation']['waypoints']['A']['yaw']==.4
        missions=c.get('/api/missions').json()
        assert missions['active'] is None
        assert [q['name'] for q in missions['queue']]==['Pending job']
        assert missions['templates'][0]['name']=='Template'
        assert {h['status'] for h in missions['history']}=={'completed','interrupted'}
        assert c.get('/api/sensors/camera').json()['status']=='NOT_CONNECTED'
        assert status['diagnostics']['interfaces']['ros2']['connected'] is False
    finally:stop(process,c,log)


def test_launcher_rejects_lan_and_bad_port_without_opening_data(tmp_path):
    for overrides,expected in [({'APP_MODE':'lan'},'LAN is disabled'),({'DASHBOARD_PORT':'bad','APP_MODE':'local'},'DASHBOARD_PORT')]:
        env={**os.environ,'MISSION_DB_PATH':str(tmp_path/'unused.sqlite3'),**overrides}
        result=subprocess.run([str(ROOT/'start-dashboard.sh'),'--no-build'],env=env,text=True,capture_output=True,timeout=10)
        assert result.returncode!=0
        assert expected in result.stdout+result.stderr
        assert not (tmp_path/'unused.sqlite3').exists()
