import asyncio
import sqlite3
import json
import os
import time
from contextlib import asynccontextmanager, suppress
from uuid import uuid4
from pathlib import Path
from typing import Literal
from fastapi import Request, FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from .models import command_adapter, ConfigurationCommand, WaypointCommand
from .configuration import ConfigurationStore, ConfigurationError, ConfigurationConflict
from .exports import filter_events, csv_export
from .security import Security, SecurityMiddleware, COOKIE
from .simulator import RobotSimulator
from .operations import DefinitionStore, MissionDefinition, OperationsCommand
from pydantic import TypeAdapter
from .models import ControlCommand, NavigationCommand, WaypointCommand, ConfigurationCommand
operations_adapter = TypeAdapter(ControlCommand | NavigationCommand | WaypointCommand | ConfigurationCommand | OperationsCommand)

@asynccontextmanager
async def lifespan(app):
    app.state.security = Security()
    path = os.getenv("ROBOT_CONFIG_PATH", str(Path(__file__).resolve().parents[1] / "data" / "robot-config.json"))
    store = None if path == ":memory:" else ConfigurationStore(path)
    database = os.getenv("MISSION_DB_PATH", str(Path(__file__).resolve().parents[1] / "data" / "missions.sqlite3"))
    app.state.robot = RobotSimulator(store=store, operations_store=DefinitionStore(database))
    async def simulate():
        previous = time.monotonic()
        while True:
            await asyncio.sleep(0.1)
            now = time.monotonic()
            try:app.state.robot.tick(min(now - previous, 0.25))
            except sqlite3.Error:
                robot=app.state.robot;robot.halt();robot.owner=None
                if not robot.operations.persistence_fault:robot.log('error','Mission storage failure: motion halted; repair storage and restart.')
                robot.operations.persistence_fault=True
                if robot.operations.current:robot.operations.current.update(status='paused',reason='Storage fault; repair and restart required')
                if robot.mission.status=='running':robot.mission.status='paused'
            previous = now
    task = asyncio.create_task(simulate())
    try:
        yield
    finally:
        app.state.robot.halt()
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        try:
            app.state.robot.operations.finish("interrupted", "Service shutdown; explicit restart required")
            app.state.robot.stop("Service shutdown")
        finally:
            app.state.robot.operations.store.close()

app = FastAPI(title="PBL4 AMR Simulation API", lifespan=lifespan)
origins = os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type","X-CSRF-Token"], allow_credentials=True)

app.add_middleware(SecurityMiddleware)

@app.get('/api/auth/session')
async def auth_session(request:Request):
    security=app.state.security;session=security.session(request.cookies)
    local=security.local(request.scope)
    return {'role':'operator' if local else session['role'] if session else None,
            'authenticated':local or session is not None,'username':'local-developer' if local else session['username'] if session else None,
            'csrf':session['csrf'] if session else '', 'mode':'lan' if security.lan else 'local'}

@app.post('/api/auth/login')
async def login(request:Request):
    security=app.state.security
    if not security.rate(('login',request.client.host),5):raise HTTPException(429,'Too many login attempts; retry in a minute')
    try:payload=await request.json();password=payload.get('password','');name=payload.get('username','')
    except (ValueError,AttributeError):raise HTTPException(400,'Password required')
    if not isinstance(password,str) or len(password)>256 or not isinstance(name,str) or len(name)>64:raise HTTPException(400,'Invalid credentials format')
    token=security.login(name,password)
    if token is None:raise HTTPException(401,'Invalid credentials')
    security.sessions.pop(request.cookies.get(COOKIE,''),None)
    response=Response('{}',media_type='application/json')
    response.set_cookie(COOKIE,token,max_age=28800,httponly=True,secure=True,samesite='strict',path='/')
    return response

@app.post('/api/auth/logout')
async def logout(request:Request):
    app.state.security.sessions.pop(request.cookies.get(COOKIE,''),None)
    response=Response('{}',media_type='application/json');response.delete_cookie(COOKIE,path='/',secure=True,httponly=True,samesite='strict');return response

@app.get("/api/health")
def health():
    return {"status": "ok", "simulation": True, "hardware_enabled": False}

@app.get("/api/robot/status")
async def status():
    return app.state.robot.snapshot()

@app.get("/api/map")
async def map_data():
    return app.state.robot.grid.snapshot()

@app.get("/api/configuration")
async def configuration():
    return app.state.robot.configuration.snapshot()


def apply_configuration(command):
    robot = app.state.robot
    try:
        robot.command(command, "http-configuration")
    except ConfigurationError as exc:
        robot.counters["rejected_commands"] += 1
        robot.log("error" if "save failed" in str(exc) else "warning", str(exc))
        raise HTTPException(status_code=409 if isinstance(exc, ConfigurationConflict) else 400, detail=str(exc)) from exc
    return robot.configuration.snapshot()


@app.post("/api/configuration")
async def update_configuration(command: ConfigurationCommand):
    return apply_configuration(command)


@app.post("/api/waypoints")
async def update_waypoint(command: WaypointCommand):
    return apply_configuration(command)


@app.get("/api/events")
async def events(level: Literal["all", "info", "warning", "error"] = "all",
                 q: str = Query(default="", max_length=200), format: Literal["json", "csv"] = "json"):
    rows = filter_events(app.state.robot.events, level, q)
    if format == "csv":
        return Response(csv_export(rows, ["id", "time", "level", "message"]), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="pbl4-events.csv"'})
    return {"events": rows, "capacity": 60, "timestamp_format": "UTC ISO 8601"}


@app.get("/api/diagnostics/history")
async def history(limit: int = Query(default=600, ge=1, le=600), format: Literal["json", "csv"] = "json"):
    rows = list(app.state.robot.history)[-limit:]
    if format == "csv":
        columns = list(rows[0]) if rows else ["timestamp"]
        return Response(csv_export(rows, columns), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="pbl4-telemetry.csv"'})
    return {"samples": rows, "capacity": 600, "source": "simulation", "session_id": app.state.robot.session_id}


@app.websocket("/ws/telemetry")
async def telemetry(socket: WebSocket):
    if socket.headers.get("origin") not in app.state.security.origins and socket.headers.get("origin") is not None:
        await socket.close(code=1008)
        return
    await socket.accept()
    robot = app.state.robot
    client = str(uuid4())
    security=app.state.security
    controller=security.operator(socket)
    async def receive():
        while True:
            try:
                raw = await socket.receive_text()
                if len(raw.encode("utf-8")) > 2048:
                    raise ValueError("Command too large")
                if not controller or not security.operator(socket):
                    await socket.send_json({"type":"error","message":"Authenticated operator required; observer connection is read-only."});await socket.close(code=1008);return
                if not security.rate(("ws",client),40,1) and json.loads(raw).get("type")!="stop":
                    await socket.close(code=1008,reason="Control message rate exceeded");return
                robot.counters["ws_rx_frames"] += 1
                command = operations_adapter.validate_python(json.loads(raw))
                if not robot.command(command, client):
                    await socket.send_json({"type": "error", "message": "Control is reserved by another client or mode. Cancel autonomous navigation before manual driving."})
                elif command.type not in ("heartbeat", "control", "release"):
                    await socket.send_json({"type": "ack"})
            except sqlite3.Error:
                robot.halt();robot.disconnect(client)
                await socket.send_json({'type':'error','message':'Storage failure; motion halted. Repair storage and restart.'})
            except ConfigurationError as exc:
                robot.counters["rejected_commands"] += 1
                robot.log("error" if "save failed" in str(exc) else "warning", str(exc))
                await socket.send_json({"type": "error", "message": str(exc)[:200]})
            except ValidationError:
                robot.counters["rejected_commands"] += 1
                await socket.send_json({"type": "error", "message": "Invalid control command. Controller commands cleared."})
            except json.JSONDecodeError:
                robot.counters["rejected_commands"] += 1
                await socket.send_json({"type": "error", "message": "Invalid control command. Controller commands cleared."})
            except ValueError as exc:
                robot.counters["rejected_commands"] += 1
                await socket.send_json({"type": "error", "message": str(exc)[:180]})
    async def send():
        while True:
            if not security.authenticated(socket):
                await socket.close(code=1008,reason="Authentication expired or revoked");return
            await socket.send_text(robot.broadcast_text())
            await asyncio.sleep(0.1)
    tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (WebSocketDisconnect, RuntimeError, OSError, asyncio.CancelledError):
        pass
    finally:
        robot.disconnect(client)
        for task in tasks:
            task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.gather(*tasks, return_exceptions=True)


@app.get("/api/sensors")
async def sensors():
    return {"session_id": app.state.robot.session_id, **app.state.robot.sensors.snapshot(include_data=False)}


@app.get("/api/sensors/lidar")
async def lidar():
    return app.state.robot.sensors.snapshot()["lidar"]


@app.get("/api/sensors/camera")
async def camera():
    return app.state.robot.sensors.snapshot()["camera"]


@app.websocket("/ws/sensors")
async def sensor_stream(socket: WebSocket):
    if socket.headers.get("origin") not in app.state.security.origins and socket.headers.get("origin") is not None:
        await socket.close(code=1008)
        return
    await socket.accept()
    robot = app.state.robot

    async def publish():
        previous = None
        while True:
            if not app.state.security.authenticated(socket):
                await socket.close(code=1008,reason="Authentication expired or revoked");return
            bundle = robot.sensors.snapshot()
            signature = tuple((bundle[name]["sequence"], bundle[name]["status"], bundle[name]["error"])
                              for name in ("lidar", "camera"))
            if signature != previous:
                await socket.send_json({"type": "sensors", "simulation": True,
                                        "session_id": robot.session_id, **bundle})
                previous = signature
            await asyncio.sleep(0.2)

    async def receive():
        await socket.receive_text()
        await socket.close(code=1008, reason="Read-only sensor stream; controls use /ws/telemetry")

    tasks = [asyncio.create_task(publish()), asyncio.create_task(receive())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (WebSocketDisconnect, RuntimeError, OSError, asyncio.CancelledError):
        pass
    finally:
        for task in tasks:
            task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.gather(*tasks, return_exceptions=True)


@app.get('/api/missions')
async def mission_operations():
    r=app.state.robot.operations
    return {**r.snapshot(),'history':r.history(limit=200),'analytics':r.analytics()}

@app.post('/api/missions')
async def create_mission(definition: MissionDefinition, template: bool=False):
    try:return app.state.robot.operations.create(definition,template)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc

@app.post('/api/missions/queue/order')
async def reorder_missions(ids:list[str]):
    try:app.state.robot.operations.reorder(ids)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
    return {'status':'ok'}

@app.delete('/api/missions/queue')
async def clear_missions(confirm:bool=False):
    if not confirm:raise HTTPException(400,'Explicit confirmation is required to clear the queue')
    ops=app.state.robot.operations;ops.store.replace('queue',[]);ops.queue=[]
    return {'status':'ok'}

@app.delete('/api/missions/{id}')
async def remove_mission(id:str,template:bool=False):
    try:app.state.robot.operations.remove(id,template)
    except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    return {'status':'ok'}

@app.get('/api/missions/history')
async def mission_history(status:Literal['all','completed','cancelled','failed','interrupted']='all',q:str=Query('',max_length=200),format:Literal['json','csv']='json'):
    operations=app.state.robot.operations
    rows=operations.history(status,q,limit=None if format=='csv' else 1000)
    if format=='csv':
        columns=['id','mission_id','name','started_at','finished_at','duration','status','distance','completed_steps','waypoint_visits','reason','start_pose','end_pose','steps']
        export_rows=[{**r,'steps':json.dumps(r['steps']),'start_pose':json.dumps(r['start_pose']),'end_pose':json.dumps(r['end_pose'])} for r in rows]
        return Response(csv_export(export_rows,columns),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="pbl4-missions.csv"'})
    return {'records':rows,'total':operations.store.history_count(status,q)}
