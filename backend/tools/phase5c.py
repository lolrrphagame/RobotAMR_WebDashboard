"""Bounded, isolated Phase 5C profiling and HTTPS acceptance/soak runner."""
import argparse
from collections import deque
import gzip
import json
import os
from pathlib import Path
import platform
import queue
import secrets
import signal
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))


def percentile(values, fraction=.95):
    values = sorted(values)
    return values[min(len(values)-1, int((len(values)-1)*fraction))] if values else None


def micro():
    from app.simulator import RobotSimulator
    robot = RobotSimulator()
    results = {}
    for label, function, count in (
        ('physics_tick', lambda: robot.tick(.1), 200),
        ('lidar_scan', lambda: robot.sensors.lidar.capture(tuple(robot.state.pose), robot.sample_timestamp, time.monotonic()), 200),
        ('snapshot_json', lambda: json.dumps(robot.snapshot(), separators=(',', ':'), ensure_ascii=False, allow_nan=False), 200),
    ):
        durations=[]
        for _ in range(count):
            before=time.perf_counter(); function(); durations.append((time.perf_counter()-before)*1000)
        results[label]={'samples':count,'mean_ms':sum(durations)/count,'p95_ms':percentile(durations)}
    durations=[]
    for _ in range(200):
        robot.tick(.1)
        before=time.perf_counter()
        for consumer in range(4):
            if hasattr(robot, 'broadcast_text'): robot.broadcast_text()
            else: json.dumps(robot.broadcast_snapshot(), separators=(',', ':'), ensure_ascii=False, allow_nan=False)
        durations.append((time.perf_counter()-before)*1000)
    results['four_consumer_serialization']={'mean_ms':sum(durations)/len(durations),'p95_ms':percentile(durations)}
    for index in range(1000):
        robot.operations.store.save_run({'id':str(index),'name':f'Archive {index}','status':'completed','duration':1.,
            'distance':.1,'waypoint_visits':1,'started_at':'2026-11-22T00:00:00+00:00','steps':[{'kind':'wait','status':'completed'}]*16})
    durations=[]
    for _ in range(30):
        before=time.perf_counter()
        try: robot.operations.history(limit=200)
        except TypeError: robot.operations.history()[:200]
        robot.operations.analytics()
        durations.append((time.perf_counter()-before)*1000)
    results['archive_1000_history_and_analytics']={'samples':30,'mean_ms':sum(durations)/len(durations),'p95_ms':percentile(durations)}
    robot.operations.store.close()
    results['bundle']=[{'file':str(path.relative_to(ROOT/'frontend/dist')),'bytes':path.stat().st_size,
                        'gzip_bytes':len(gzip.compress(path.read_bytes(),mtime=0))}
                       for path in sorted((ROOT/'frontend/dist').rglob('*')) if path.is_file()]
    results['environment']={'machine':platform.machine(),'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,
                            'logical_cpus':os.cpu_count(),'note':'Laptop measurements; not Raspberry Pi results.'}
    return results


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));return listener.getsockname()[1]


def process_sample(pid):
    fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
    return {'cpu_seconds':(int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK'),
            'rss_mib':int(fields[21])*os.sysconf('SC_PAGE_SIZE')/1024**2,
            'fds':len(list(Path(f'/proc/{pid}/fd').iterdir()))}


class Stream(threading.Thread):
    def __init__(self, url, origin, context, cookie, kind, operator=False):
        super().__init__(daemon=True)
        self.url,self.origin,self.context,self.cookie,self.kind,self.operator=url,origin,context,cookie,kind,operator
        self.cancel=threading.Event();self.ready=threading.Event();self.commands=queue.Queue(maxsize=8)
        self.frames=self.bytes=0;self.errors=deque(maxlen=20);self.latest=None
        self.expected_close=False
    def run(self):
        from websockets.sync.client import connect
        try:
            with connect(self.url, ssl=self.context, origin=self.origin, additional_headers={'Cookie':self.cookie}, proxy=None, open_timeout=5) as ws:
                last_heartbeat=0
                self.ready.set()
                while not self.cancel.is_set():
                    now=time.monotonic()
                    if self.operator and now-last_heartbeat>=.15:
                        ws.send('{"type":"heartbeat"}');last_heartbeat=now
                    try: ws.send(json.dumps(self.commands.get_nowait()))
                    except queue.Empty:pass
                    try: raw=ws.recv(timeout=.05)
                    except TimeoutError:continue
                    self.frames+=1;self.bytes+=len(raw.encode() if isinstance(raw,str) else raw)
                    frame=json.loads(raw)
                    if frame.get('type')=='error':self.errors.append(frame['message'])
                    elif frame.get('type') in ('telemetry','sensors'):self.latest=frame
        except Exception as exc:
            if not self.expected_close:self.errors.append(type(exc).__name__+': '+str(exc))
    def stop(self):
        self.expected_close=True;self.cancel.set();self.join(timeout=5)
        if self.is_alive():raise RuntimeError('Stream worker failed to close')
        self.latest=None


def soak(seconds, observers):
    import httpx
    from app.accounts import AccountStore, make_password_hash
    from app.backup import backup
    results={'duration_seconds':seconds,'observers':observers,'checks':{},'errors':[],'resources':[]}
    with tempfile.TemporaryDirectory(prefix='pbl4-phase5c-') as temporary:
        data=Path(temporary);data.chmod(0o700)
        password=secrets.token_urlsafe(24)
        store=AccountStore(data/'accounts.json')
        encoded=make_password_hash(password)
        store.create('operator','operator',encoded);store.create('observer','observer',encoded)
        port,upstream=free_port(),free_port()
        origin=f'https://127.0.0.1:{port}'
        config={'APP_MODE':'lan','LAN_HOST':'127.0.0.1','LAN_BIND_IP':'127.0.0.1','HTTPS_PORT':str(port),
                'BACKEND_PORT':str(upstream),'ALLOWED_HOSTS':'127.0.0.1','ALLOWED_ORIGINS':origin,
                'ACCOUNT_STORE_PATH':str(store.path),'CADDY_BIN':str(ROOT/'.tools/caddy'),'TLS_MODE':'internal',
                'LAN_STATE_DIR':str(data/'runtime'),'MISSION_DB_PATH':str(data/'missions.sqlite3'),
                'ROBOT_CONFIG_PATH':str(data/'robot-config.json')}
        envfile=data/'lan.env';envfile.write_text('\n'.join(k+'='+v for k,v in config.items()));envfile.chmod(0o600)
        process=None;client=None;streams=[];server_log=(data/'server.log').open('w+')
        def start():
            nonlocal process,client
            process=subprocess.Popen([str(ROOT/'start-dashboard-lan.sh'),'--config',str(envfile)],cwd=ROOT,
                                     stdout=server_log,stderr=subprocess.STDOUT,start_new_session=True)
            ca=data/'runtime/data/caddy/pki/authorities/local/root.crt'
            for _ in range(200):
                if process.poll() is not None:break
                if ca.exists():
                    if client is None:client=httpx.Client(base_url=origin,verify=ssl.create_default_context(cafile=str(ca)),trust_env=False,timeout=3)
                    try:
                        if client.get('/api/health').status_code==200:return
                    except httpx.HTTPError:pass
                time.sleep(.05)
            raise RuntimeError('Isolated server startup failed: '+(data/'server.log').read_text()[-3000:])
        def shutdown():
            if process and process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:process.wait(timeout=25)
                except subprocess.TimeoutExpired:process.kill();process.wait();raise RuntimeError('Server did not shut down gracefully')
        def login(name):
            response=client.post('/api/auth/login',json={'username':name,'password':password},headers={'Origin':origin})
            response.raise_for_status()
            state=client.get('/api/auth/session').json()
            return '; '.join(f'{c.name}={c.value}' for c in client.cookies.jar),{'Origin':origin,'X-CSRF-Token':state['csrf']}
        def connect(cookie,kind='telemetry',operator=False):
            stream=Stream(origin.replace('https:','wss:')+'/ws/'+kind,origin,
                          ssl.create_default_context(cafile=str(data/'runtime/data/caddy/pki/authorities/local/root.crt')),
                          cookie,kind,operator)
            streams.append(stream);stream.start()
            if not stream.ready.wait(5):raise RuntimeError('Stream did not connect')
            return stream
        def command(stream,body):stream.commands.put(body,timeout=1)
        def status():return client.get('/api/robot/status').json()
        def wait_for(predicate,timeout=5):
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                value=status()
                if predicate(value):return value
                time.sleep(.05)
            raise AssertionError('Timed out waiting for safe state')
        try:
            start();results['checks']['anonymous_data_denied']=client.get('/api/map').status_code==401
            operator_cookie,headers=login('operator')
            client.cookies.clear();observer_cookie,_=login('observer')
            results['checks']['observer_mutation_denied']=client.post('/api/missions',json={},headers={'Origin':origin}).status_code==403
            client.cookies.clear();client.cookies.set('pbl4_session',operator_cookie.split('=',1)[1])
            client.post('/api/configuration',json={'type':'configuration','action':'set_home','goal':{'x':1,'y':1,'yaw':0}},headers=headers).raise_for_status()
            client.post('/api/waypoints',json={'type':'waypoint','name':'A','goal':{'x':1.2,'y':1,'yaw':0}},headers=headers).raise_for_status()
            owner=connect(operator_cookie,operator=True);connect(operator_cookie,'sensors')
            observer_streams=[]
            for _ in range(observers):observer_streams.append(connect(observer_cookie));connect(observer_cookie,'sensors')
            children=Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()
            pids={('backend' if b'--backend' in Path(f'/proc/{pid}/cmdline').read_bytes() else 'caddy'):int(pid) for pid in children}
            started=time.monotonic();baseline={name:process_sample(pid) for name,pid in pids.items()}
            last_metrics=last_job=last_reconnect=started;cycles=0;http_latencies=deque(maxlen=3600)
            while time.monotonic()-started<seconds:
                now=time.monotonic()
                if now-last_job>=4:
                    current=status()
                    if current['operations']['active'] is None:
                        response=client.post('/api/missions',json={'name':f'Soak {cycles}','steps':[{'kind':'wait','seconds':.2},{'kind':'pose','pose':{'x':1.2,'y':1,'yaw':0}},{'kind':'home'}]},headers=headers)
                        response.raise_for_status();command(owner,{'type':'operations','action':'start_next'});cycles+=1
                    last_job=now
                if observers and now-last_reconnect>=5:
                    observer_streams[0].stop();observer_streams[0]=connect(observer_cookie);last_reconnect=now
                if now-last_metrics>=1:
                    sample={'elapsed':now-started,**{name:process_sample(pid) for name,pid in pids.items()}}
                    results['resources'].append(sample)
                    before=time.perf_counter();client.get('/api/diagnostics/history').raise_for_status()
                    client.get('/api/missions').raise_for_status();http_latencies.append((time.perf_counter()-before)*1000)
                    last_metrics=now
                if process.poll() is not None:raise RuntimeError('Server exited during load')
                time.sleep(.05)
            elapsed=time.monotonic()-started
            end={name:process_sample(pid) for name,pid in pids.items()}
            results['processes']={name:{'cpu_percent_one_core':100*(end[name]['cpu_seconds']-first['cpu_seconds'])/elapsed,
                'rss_start_mib':first['rss_mib'],'rss_end_mib':end[name]['rss_mib'],'rss_delta_mib':end[name]['rss_mib']-first['rss_mib'],
                'fds_start':first['fds'],'fds_end':end[name]['fds']} for name,first in baseline.items()}
            results['elapsed_seconds']=elapsed;results['mission_cycles_started']=cycles
            results['http_history_plus_missions_p95_ms']=percentile(http_latencies)
            results['streams']={kind:{'frames':sum(s.frames for s in streams if s.kind==kind),
                'json_bytes':sum(s.bytes for s in streams if s.kind==kind)} for kind in ('telemetry','sensors')}
            results['completed_before_stop']=client.get('/api/missions').json()['analytics']['completed']
            results['checks']['missions_execute']=cycles>=1 and (seconds<30 or results['completed_before_stop']>=1)
            results['observer_reconnects']=sum(s.kind=='telemetry' and not s.operator for s in streams)-observers
            # STOP during navigation and explicit cancellation, without changing motion logic.
            command(owner,{'type':'stop'});wait_for(lambda s:s['operations']['active'] is None)
            command(owner,{'type':'navigation','action':'start','goal':{'x':2,'y':1,'yaw':0}})
            wait_for(lambda s:s['navigation']['status']=='running')
            command(owner,{'type':'stop'});wait_for(lambda s:s['navigation']['status']=='idle' and all(m['actual_rpm']==0 for m in s['motors']))
            results['checks']['stop_navigation']=True
            command(owner,{'type':'navigation','action':'start','goal':{'x':2,'y':1,'yaw':0}})
            wait_for(lambda s:s['navigation']['status']=='running')
            command(owner,{'type':'navigation','action':'cancel'});wait_for(lambda s:s['navigation']['status']=='idle')
            results['checks']['cancel_navigation']=True
            command(owner,{'type':'release'})  # STOP deliberately inhibits held input until release.
            command(owner,{'type':'control','linear':.1});wait_for(lambda s:s['mode']=='MANUAL')
            for stream in streams:
                if stream.cookie==operator_cookie:stream.expected_close=True
            client.post('/api/auth/logout',headers=headers).raise_for_status()
            # Observe safety through a separate authenticated Observer session.
            client.cookies.clear();client.cookies.set('pbl4_session',observer_cookie.split('=',1)[1])
            wait_for(lambda s:all(m['actual_rpm']==0 for m in s['motors']) and s['mode']=='STANDBY')
            results['checks']['logout_during_motion']=True
            for stream in streams:stream.stop()
            time.sleep(.2)
            results['resources_after_stream_cleanup']={name:process_sample(pid) for name,pid in pids.items()}
            results['checks']['socket_resource_cleanup']=all(results['resources_after_stream_cleanup'][name]['fds']<=baseline[name]['fds'] for name in pids)
            results['errors']=[error for stream in streams for error in stream.errors][:40]
            frozen=status();results['buffers']={'history':len(client.get('/api/diagnostics/history').json()['samples']),
                'events':len(frozen['events']),'trajectory':len(frozen['trajectory'])}
            results['checks']['camera_placeholder_only']=frozen['sensors']['camera']['status']=='NOT_CONNECTED'
            result_before=client.get('/api/missions').json();ca_before=(data/'runtime/data/caddy/pki/authorities/local/root.crt').read_bytes()
            backup(data/'online-backup',data/'missions.sqlite3',data/'robot-config.json')
            with sqlite3.connect(data/'online-backup/missions.sqlite3') as online:
                results['checks']['online_wal_backup']=online.execute('SELECT count(*) FROM executions').fetchone()[0]==result_before['analytics']['total']
            shutdown();client.close();client=None
            backup(data/'backup',data/'missions.sqlite3',data/'robot-config.json')
            # Validate a copy, never restore over the source, production files or account/CA data.
            import shutil
            shutil.copy2(data/'backup/missions.sqlite3',data/'restored.sqlite3')
            with sqlite3.connect(data/'restored.sqlite3') as restored:
                results['checks']['restored_integrity']=restored.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
                results['restored_execution_count']=restored.execute('SELECT count(*) FROM executions').fetchone()[0]
            results['checks']['json_backup']=json.loads((data/'backup/robot-config.json').read_text())==json.loads((data/'robot-config.json').read_text())
            start();old_cookie=operator_cookie
            results['checks']['restart_revokes_session']=client.get('/api/map',headers={'Cookie':old_cookie}).status_code==401
            client.cookies.set('pbl4_session',observer_cookie.split('=',1)[1])
            results['checks']['observer_session_revoked']=client.get('/api/map').status_code==401
            client.cookies.clear();login('observer')
            fresh=status();saved=client.get('/api/missions').json()
            results['checks']['restart_stopped']=fresh['mode']=='STANDBY' and all(m['actual_rpm']==0 for m in fresh['motors']) and saved['active'] is None
            results['checks']['history_preserved']=saved['analytics']==result_before['analytics']
            results['checks']['home_waypoint_preserved']=fresh['home']==frozen['home'] and fresh['navigation']['waypoints']==frozen['navigation']['waypoints']
            results['checks']['ca_preserved']=(data/'runtime/data/caddy/pki/authorities/local/root.crt').read_bytes()==ca_before
            results['checks']['bounded_buffers']=results['buffers']['history']<=600 and results['buffers']['events']<=60 and results['buffers']['trajectory']<=1200
        except Exception as exc:
            results['errors'].append(type(exc).__name__+': '+str(exc))
        finally:
            for stream in streams:
                if stream.is_alive():stream.stop()
            shutdown()
            if client:client.close()
            server_log.close()
        results['passed']=all(results['checks'].values()) and not results['errors']
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--micro',action='store_true',help='bounded simulator/SQLite/bundle microbenchmarks only')
    parser.add_argument('--seconds',type=int,default=30)
    parser.add_argument('--observers',type=int,default=3)
    parser.add_argument('--output',required=True,help='New JSON report path; never overwritten')
    args=parser.parse_args()
    if not 15<=args.seconds<=3600 or not 0<=args.observers<=6:parser.error('Bound duration to 15–3600 seconds and observers to 0–6')
    output=Path(args.output)
    if output.exists():parser.error('Output already exists; select a new report path')
    results=micro() if args.micro else soak(args.seconds,args.observers)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as destination:json.dump(results,destination,indent=2)
    print(f'Report: {output}')
    if not args.micro and not results['passed']:raise SystemExit('Acceptance checks failed; inspect report')


if __name__=='__main__':main()
