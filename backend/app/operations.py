"""Mission operations reuse MissionManager for all movement. No second controller."""
import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4
from pydantic import Field, model_validator
from .models import StrictModel, Goal
from .navigation import plan_path


def utc():
    return datetime.now(timezone.utc).isoformat()


class MissionStep(StrictModel):
    kind: Literal['waypoint','pose','home','wait']
    waypoint: Literal['A','B','C'] | None = None
    pose: Goal | None = None
    seconds: float = Field(default=0, ge=0, le=3600)

    @model_validator(mode='after')
    def valid(self):
        if self.kind=='waypoint' and not self.waypoint: raise ValueError('Choose a saved waypoint')
        if self.kind=='pose' and self.pose is None: raise ValueError('A map pose is required')
        if self.kind=='wait' and self.seconds<=0: raise ValueError('WAIT duration must be positive')
        if self.kind!='wait' and self.seconds: raise ValueError('Duration belongs only to WAIT steps')
        if self.kind!='pose' and self.pose is not None: raise ValueError('Pose belongs only to pose steps')
        if self.kind!='waypoint' and self.waypoint is not None: raise ValueError('Waypoint belongs only to waypoint steps')
        return self


class MissionDefinition(StrictModel):
    name: str = Field(min_length=1,max_length=80)
    steps: list[MissionStep] = Field(min_length=1,max_length=32)

    @model_validator(mode='after')
    def nonblank(self):
        self.name=self.name.strip()
        if not self.name: raise ValueError('Mission name cannot be blank')
        return self


class OperationsCommand(StrictModel):
    type: Literal['operations']
    action: Literal['start_next','pause','resume','cancel']


class DefinitionStore:
    def __init__(self,path=':memory:'):
        if path!=':memory:': Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(path),timeout=5)
        try:self.db.execute("SELECT json_valid('{}')")
        except sqlite3.OperationalError as exc:
            self.db.close()
            raise ValueError('SQLite JSON functions are required for mission history/analytics; verify the Python SQLite build before deployment') from exc
        self.db.create_function('pbl4_casefold',1,lambda value:(value or '').casefold(),deterministic=True)
        self.db.execute('PRAGMA busy_timeout=5000')
        version=self.db.execute('PRAGMA user_version').fetchone()[0]
        if version>1:self.db.close();raise ValueError('Unsupported future mission database version; no migration applied')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS definitions (id TEXT PRIMARY KEY, kind TEXT, position INTEGER, body TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS executions (id TEXT PRIMARY KEY, status TEXT, body TEXT)')
        self.db.execute('CREATE INDEX IF NOT EXISTS executions_status ON executions(status)')
        self.db.execute('PRAGMA user_version=1')
        # Live ownership is never restored. Unfinished runs become terminal records.
        for run in self.records(active_only=True):
            if run['status'] in ('running','paused'):
                for step in run['steps']:
                    if step['status']=='running':step.update(status='interrupted',finished_at=utc())
                run.update(status='interrupted',finished_at=utc(),reason='Backend restart; explicit operator action required')
                self.save_run(run)

    def definitions(self,kind):
        return [json.loads(row[0]) for row in self.db.execute('SELECT body FROM definitions WHERE kind=? ORDER BY position,id',(kind,))]

    def replace(self,kind,items):
        with self.db:
            self.db.execute('DELETE FROM definitions WHERE kind=?',(kind,))
            self.db.executemany('INSERT INTO definitions VALUES (?,?,?,?)',[(v['id'],kind,i,json.dumps(v)) for i,v in enumerate(items)])

    def save_run(self,run):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO executions VALUES (?,?,?)',(run['id'],run['status'],json.dumps(run)))

    def records(self,active_only=False):
        query="SELECT body FROM executions" + (" WHERE status IN ('running','paused')" if active_only else '') + " ORDER BY rowid DESC"
        return [json.loads(row[0]) for row in self.db.execute(query)]

    def history_filter(self,status,query):
        where="status NOT IN ('running','paused')"
        parameters=[]
        if status!='all':where+=' AND status=?';parameters.append(status)
        if query:
            where+=" AND instr(pbl4_casefold(json_extract(body,'$.name')),?)>0"
            parameters.append(query.casefold())
        return where,parameters

    def history(self,status='all',query='',limit=None):
        where,parameters=self.history_filter(status,query)
        sql='SELECT body FROM executions WHERE '+where+' ORDER BY rowid DESC'
        if limit is not None:sql+=' LIMIT ?';parameters.append(limit)
        return [json.loads(row[0]) for row in self.db.execute(sql,parameters)]

    def history_count(self,status='all',query=''):
        where,parameters=self.history_filter(status,query)
        return self.db.execute('SELECT count(*) FROM executions WHERE '+where,parameters).fetchone()[0]

    def analytics(self):
        # Aggregate inside SQLite instead of retaining/decoding the whole archive in Python.
        where="status NOT IN ('running','paused')"
        row=self.db.execute("""SELECT count(*),
            coalesce(sum(status='completed'),0),coalesce(sum(status='cancelled'),0),
            coalesce(sum(status='failed'),0),coalesce(sum(status='interrupted'),0),
            coalesce(avg(json_extract(body,'$.duration')),0),
            coalesce(sum(json_extract(body,'$.distance')),0),
            coalesce(sum(json_extract(body,'$.waypoint_visits')),0)
            FROM executions WHERE """+where).fetchone()
        trends=self.db.execute("SELECT substr(json_extract(body,'$.started_at'),1,10),count(*) FROM executions WHERE "+where+' GROUP BY 1 ORDER BY 1').fetchall()
        return dict(total=row[0],completed=row[1],cancelled=row[2],failed=row[3],interrupted=row[4],
                    success_rate=row[1]/row[0]*100 if row[0] else 0,average_duration=row[5],distance=row[6],
                    waypoint_visits=row[7],trends=[{'date':day,'missions':count} for day,count in trends])

    def close(self):
        try:self.db.execute('PRAGMA wal_checkpoint(PASSIVE)')
        finally:self.db.close()


class Operations:
    def __init__(self,robot,store=None):
        self.robot=robot;self.store=store or DefinitionStore();self.current=None;self.persistence_fault=False
        self.queue=[];self.templates=[];self.checkpoint=0
        for kind in ('queue','template'):
            valid=[]
            for definition in self.store.definitions(kind):
                try:
                    self.validate(MissionDefinition.model_validate(definition['definition']))
                    valid.append(definition)
                except ValueError:
                    robot.log('warning',f"Invalid restored {kind} skipped: {definition.get('name','unnamed')}")
            setattr(self,'queue' if kind=='queue' else 'templates',valid[:20 if kind=='queue' else 50])

    @property
    def active(self): return self.current is not None

    def resolve(self,step):
        r=self.robot
        if step.kind=='home': return r.configuration.value.home.model_copy()
        if step.kind=='pose': return step.pose.model_copy()
        if step.kind=='waypoint':
            if step.waypoint not in r.mission.waypoints: raise ValueError(f'Waypoint {step.waypoint} is not saved')
            return r.mission.waypoints[step.waypoint].model_copy()
        return None

    def validate(self,definition):
        for step in definition.steps:
            goal=self.resolve(step)
            if goal is not None: self.robot.configuration.validate_pose(goal,'Mission destination')

    def create(self,definition,template=False):
        self.validate(definition)
        items=list(self.templates if template else self.queue)
        if len(items)>=(50 if template else 20): raise ValueError('Template capacity is 50' if template else 'Queue capacity is 20')
        item={'id':uuid4().hex,'name':definition.name,'created_at':utc(),'definition':definition.model_dump()}
        items.append(item);self.store.replace('template' if template else 'queue',items)
        if template:self.templates=items
        else:self.queue=items
        self.robot.log('info',f"Mission {'template saved' if template else 'created and queued'}: {definition.name}")
        return item

    def reorder(self,ids):
        if len(ids)!=len(self.queue) or set(ids)!={i['id'] for i in self.queue}: raise ValueError('Order must contain every pending mission exactly once')
        by_id={i['id']:i for i in self.queue};items=[by_id[i] for i in ids]
        self.store.replace('queue',items);self.queue=items

    def remove(self,id,template=False):
        items=self.templates if template else self.queue
        if not any(i['id']==id for i in items): raise ValueError('Mission definition no longer exists; refresh the queue')
        updated=[i for i in items if i['id']!=id];self.store.replace('template' if template else 'queue',updated)
        if template:self.templates=updated
        else:self.queue=updated

    def start(self,client):
        r=self.robot
        if self.persistence_fault:raise ValueError('Storage fault; repair storage and restart')
        if self.active or r.owner is not None or r.mission.active: raise ValueError('Robot motion is already reserved; cancel or release it first')
        if not self.queue: raise ValueError('Queue is empty')
        item=self.queue[0];definition=MissionDefinition.model_validate(item['definition']);self.validate(definition)
        # Freeze configuration references; MissionManager plans each step before movement.
        steps=[]
        for step in definition.steps:
            goal=self.resolve(step)
            steps.append({**step.model_dump(),'resolved_pose':goal.model_dump() if goal else None,'status':'pending'})
        run={'id':uuid4().hex,'mission_id':item['id'],'name':item['name'],'created_at':item['created_at'],
             'steps':steps,'status':'running','current_step':0,'completed_steps':0,'progress':0,
             'started_at':utc(),'finished_at':None,'duration':0.0,'distance':0.0,'waypoint_visits':0,
             'start_pose':list(r.state.pose),'end_pose':list(r.state.pose),'reason':None,'step_started':False,'wait_remaining':0}
        # Queue removal and execution insertion are one SQLite transaction.
        with self.store.db:
            self.store.db.execute('DELETE FROM definitions WHERE id=?',(item['id'],))
            self.store.db.execute('INSERT INTO executions VALUES (?,?,?)',(run['id'],'running',json.dumps(run)))
        self.queue=self.queue[1:];self.current=run;r.halt();r.mission.reset()
        r.owner=client;r.last_lease=time.monotonic();r.safety.update(stop_active=False,watchdog='armed_autonomous')
        r.log('info',f"Mission started: {run['name']}")

    def pause(self,reason='Operator paused mission',release=False):
        if not self.active:return
        r=self.robot;self.current.update(status='paused',reason=reason)
        r.halt()
        if r.mission.status=='running':r.mission.status='paused'
        if release:r.owner=None
        r.safety['watchdog']='paused';self.store.save_run(self.current);r.log('warning',f'Mission paused: {reason}')

    def resume(self,client):
        r=self.robot
        if self.persistence_fault:raise ValueError('Storage fault; repair storage and restart')
        if not self.current or self.current['status']!='paused':raise ValueError('No paused operations mission')
        if r.owner not in (None,client):raise ValueError('Another operator owns this mission')
        if r.mission.status=='paused':r.mission.replan_remaining(r.state.pose)
        self.current.update(status='running',reason=None);r.owner=client;r.last_lease=time.monotonic()
        r.safety.update(stop_active=False,watchdog='armed_autonomous');self.store.save_run(self.current);r.log('info','Operations mission resumed explicitly')

    def finish(self,status,reason):
        if not self.current:return
        r=self.robot;run=self.current
        if run['step_started'] and run['current_step']<len(run['steps']):run['steps'][run['current_step']]['status']=status
        run.update(status=status,reason=reason,finished_at=utc(),end_pose=list(r.state.pose))
        if status=='completed':run['progress']=100
        r.halt();r.owner=None;r.mission.reset(reason)
        try:self.store.save_run(run)
        except sqlite3.Error:
            self.persistence_fault=True
            r.log('error','Mission result could not be saved; motion halted. Repair storage and restart.')
        finally:self.current=None
        r.log('info' if status=='completed' else 'warning',f"Mission {status}: {run['name']} · {reason}")
        self.current=None

    def complete_step(self):
        run=self.current
        if not run:return
        step=run['steps'][run['current_step']];step['status']='completed';step['finished_at']=utc()
        if step['kind']=='waypoint':run['waypoint_visits']+=1
        run['completed_steps']+=1;run['current_step']+=1;run['step_started']=False
        run['progress']=100*run['completed_steps']/len(run['steps'])
        self.robot.log('info',f"Step completed / destination reached: {run['completed_steps']} of {len(run['steps'])}")
        if run['current_step']==len(run['steps']):self.finish('completed','All mission steps completed')
        else:self.store.save_run(run)

    def before_tick(self,dt):
        run=self.current
        if not run or run['status']!='running' or self.robot.owner is None:return
        run['duration']+=dt
        if not run['step_started']:
            step=run['steps'][run['current_step']]
            try:
                if step['kind']=='wait':run['wait_remaining']=step['seconds']
                else:
                    self.robot.mission.prepare(self.robot.state.pose,[Goal.model_validate(step['resolved_pose'])])
                    self.robot.mission.status='running'
                run['step_started']=True;step.update(status='running',started_at=utc())
                self.robot.log('info',f"Step started: {step['kind']} ({run['current_step']+1}/{len(run['steps'])})")
                self.store.save_run(run)
            except ValueError as exc:self.finish('failed',str(exc));return
        if self.current and run['steps'][run['current_step']]['kind']=='wait':
            run['wait_remaining']=max(0,run['wait_remaining']-dt)
            if run['wait_remaining']<=1e-9:self.complete_step()

    def after_tick(self,dt,previous_pose):
        if not self.current or self.persistence_fault:return
        if self.current['status']=='running':
            self.current['end_pose']=list(self.robot.state.pose)
            if self.current['step_started']:
                step=self.current['steps'][self.current['current_step']]
                fraction=(1-self.current['wait_remaining']/step['seconds']) if step['kind']=='wait' else self.robot.mission.progress/100
                self.current['progress']=100*(self.current['completed_steps']+fraction)/len(self.current['steps'])
            if self.robot.mission.status=='blocked':self.finish('failed',self.robot.mission.reason);return
        self.checkpoint+=dt
        if self.checkpoint>=1:self.store.save_run(self.current);self.checkpoint=0

    def snapshot(self):return {'active':self.current,'queue':self.queue,'templates':self.templates,'capacity':20}

    def history(self,status='all',query='',limit=None):
        return self.store.history(status,query,limit)

    def analytics(self):
        return self.store.analytics()
